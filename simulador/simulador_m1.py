import json
import random
from pathlib import Path
from typing import Dict, Generator, List, Optional

from utils.contratos import Event, EventType, Card, Hand


class Deck:
    """Representa uno o más mazos de cartas estándar (utilitario; no esencial si usas shoe)."""

    def __init__(self, num_decks: int = 8):
        self.num_decks = num_decks
        self.cards: List[Card] = []
        ranks = list("23456789TJQKA")
        suits = ["H", "D", "C", "S"]
        for _ in range(num_decks):
            for s in suits:
                for r in ranks:
                    self.cards.append(Card(r, s))
        self.shuffle()

    def shuffle(self) -> None:
        random.shuffle(self.cards)

    def deal(self) -> Optional[Card]:
        if not self.cards:
            return None
        return self.cards.pop()


class M1Simulator:
    """Simulador dinámico que reproduce rondas de blackjack con configuración."""

    def __init__(
        self,
        config_path: str = "configs/settings.json",
        base_bet: float = 25.0,
        event_delay: float = 0.0,   # sin sleep por defecto (rápido para pipelines)
        max_rounds: Optional[int] = None,
    ):
        self.config = self._load_config(config_path)
        rules = self.config.get("rules", {})
        self.decks = int(rules.get("decks", 6))
        self.blackjack_payout = float(rules.get("blackjack_payout", 1.5))
        self.stand_on_soft_17 = bool(rules.get("s17", True))

        self.base_bet = base_bet
        self.event_delay = event_delay  # si quisieras “tiempo real”, puedes respetarlo fuera

        self.rng = random.Random()
        self.round_counter = 0
        self.max_rounds = max_rounds

        self.shoe: List[Card] = []
        self.cut_card_threshold = 0
        self._reset_shoe()

    # ---------------- utilidades de configuración / shoe ----------------

    def _load_config(self, config_path: str) -> Dict:
        path = Path(config_path)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        # Config por defecto
        return {
            "rules": {
                "decks": 6,
                "s17": True,
                "blackjack_payout": 1.5,
            }
        }

    def _reset_shoe(self) -> None:
        ranks = list("23456789TJQKA")
        suits = ["H", "D", "C", "S"]
        self.shoe = [
            Card(rank=r, suit=s)
            for _ in range(self.decks)
            for s in suits
            for r in ranks
        ]
        self.rng.shuffle(self.shoe)
        # rebarajar cuando queden ~20% (mín. 30 cartas)
        self.cut_card_threshold = max(int(len(self.shoe) * 0.2), 30)

    def _needs_shuffle(self) -> bool:
        return len(self.shoe) <= self.cut_card_threshold

    def _draw_card(self) -> Card:
        if not self.shoe:
            self._reset_shoe()
        return self.shoe.pop()

    # ---------------- motor de simulación ----------------

    def generate_events(self) -> Generator[Event, None, None]:
        """Genera eventos de juego; respeta max_rounds si se especifica."""
        while self.max_rounds is None or self.round_counter < self.max_rounds:
            if self._needs_shuffle():
                self._reset_shoe()
                # aviso de barajado
                yield Event.create(
                    EventType.STATE_TEXT,
                    data={"phase": "shuffle", "text": "Shuffling new shoe"},
                )

            self.round_counter += 1
            round_id = f"sim_{self.round_counter:04d}"

            # inicio de ronda
            yield Event.create(EventType.ROUND_START, round_id=round_id)
            yield Event.create(
                EventType.STATE_TEXT, round_id=round_id,
                data={"phase": "bets_open", "text": "Place your bets"}
            )
            yield Event.create(
                EventType.STATE_TEXT, round_id=round_id,
                data={"phase": "dealing", "text": "Dealing cards"}
            )

            player_hand = Hand(cards=[])
            dealer_hand = Hand(cards=[])

            # reparto inicial: jugador, crupier up, jugador, crupier hole
            c1 = self._draw_card()
            up = self._draw_card()
            c2 = self._draw_card()
            hole = self._draw_card()

            player_hand.add_card(c1)
            player_hand.add_card(c2)
            dealer_hand.add_card(up)
            dealer_hand.add_card(hole)

            # eventos de cartas
            yield Event.create(
                EventType.CARD_DEALT_SHARED,
                round_id=round_id,
                cards=[str(c1), str(c2)],
                who="player_shared",
            )
            yield Event.create(
                EventType.CARD_DEALT,
                round_id=round_id,
                card=str(up),
                who="dealer_up",
            )

            # blackjack natural
            if player_hand.is_blackjack:
                if dealer_hand.is_blackjack:
                    yield Event.create(
                        EventType.CARD_DEALT,
                        round_id=round_id,
                        card=str(hole),
                        who="dealer_hole_reveal",
                    )
                    yield Event.create(
                        EventType.STATE_TEXT, round_id=round_id,
                        data={"phase": "payouts", "text": "Push: both have blackjack"}
                    )
                    yield Event.create(
                        EventType.ROUND_END,
                        round_id=round_id,
                        result="push",
                        amount=0.0,
                        reason="push_blackjack",
                        player_total=player_hand.value,
                        dealer_total=dealer_hand.value,
                    )
                    continue
                else:
                    yield Event.create(
                        EventType.STATE_TEXT, round_id=round_id,
                        data={"phase": "payouts", "text": "Blackjack! Player wins"}
                    )
                    yield Event.create(
                        EventType.ROUND_END,
                        round_id=round_id,
                        result="win",
                        amount=round(self.base_bet * self.blackjack_payout, 2),
                        reason="blackjack",
                        player_total=player_hand.value,
                        dealer_total=dealer_hand.value,
                    )
                    continue

            # turno del jugador (política simple: hit hasta 17 duro; para soft, hit <=17, hit en 18 si up >=9)
            yield Event.create(
                EventType.STATE_TEXT, round_id=round_id,
                data={"phase": "player_action", "text": "Your turn"}
            )

            while True:
                if player_hand.value >= 21:
                    break

                if self._should_player_hit(player_hand, up):
                    yield Event.create(
                        EventType.MY_DECISION_LOCKED,
                        round_id=round_id,
                        action="HIT",
                        player_total=player_hand.value,
                        dealer_up=str(up),
                    )
                    nc = self._draw_card()
                    player_hand.add_card(nc)
                    yield Event.create(
                        EventType.CARD_DEALT_SHARED,
                        round_id=round_id,
                        cards=[str(nc)],
                        who="player_shared",
                    )
                    if player_hand.is_bust:
                        break
                else:
                    yield Event.create(
                        EventType.MY_DECISION_LOCKED,
                        round_id=round_id,
                        action="STAND",
                        player_total=player_hand.value,
                        dealer_up=str(up),
                    )
                    break

            if player_hand.is_bust:
                yield Event.create(
                    EventType.STATE_TEXT, round_id=round_id,
                    data={"phase": "payouts", "text": f"Player busts with {player_hand.value}"}
                )
                yield Event.create(
                    EventType.ROUND_END,
                    round_id=round_id,
                    result="loss",
                    amount=self.base_bet,
                    reason="player_bust",
                    player_total=player_hand.value,
                    dealer_total=dealer_hand.value,
                )
                continue

            # “otros jugadores” (ruido)
            others = self.rng.randint(0, 3)
            if others > 0:
                yield Event.create(
                    EventType.STATE_TEXT, round_id=round_id,
                    data={"phase": "others_action", "text": "Others playing"}
                )
                for _ in range(others):
                    oc = self._draw_card()
                    yield Event.create(
                        EventType.CARD_DEALT,
                        round_id=round_id,
                        card=str(oc),
                        who="others_overlay",
                    )

            # turno del crupier
            yield Event.create(
                EventType.STATE_TEXT, round_id=round_id,
                data={"phase": "dealer_action", "text": "Dealer playing"}
            )
            yield Event.create(
                EventType.CARD_DEALT,
                round_id=round_id,
                card=str(hole),
                who="dealer_hole_reveal",
            )

            while self._should_dealer_hit(dealer_hand):
                nc = self._draw_card()
                dealer_hand.add_card(nc)
                yield Event.create(
                    EventType.CARD_DEALT,
                    round_id=round_id,
                    card=str(nc),
                    who="dealer_draw",
                )

            dealer_bust = dealer_hand.is_bust
            pt = player_hand.value
            dt = dealer_hand.value

            if dealer_bust:
                text = "Dealer busts! Player wins"
                result = "win"
                amount = self.base_bet
                reason = "dealer_bust"
            elif dt > pt:
                text = f"Dealer has {dt}, player has {pt}"
                result = "loss"
                amount = self.base_bet
                reason = "dealer_wins"
            elif dt < pt:
                text = f"Player wins {pt} vs {dt}"
                result = "win"
                amount = self.base_bet
                reason = "player_wins"
            else:
                text = f"Push: {pt} vs {dt}"
                result = "push"
                amount = 0.0
                reason = "push"

            yield Event.create(
                EventType.STATE_TEXT, round_id=round_id,
                data={"phase": "payouts", "text": text}
            )
            yield Event.create(
                EventType.ROUND_END,
                round_id=round_id,
                result=result,
                amount=round(amount, 2),
                reason=reason,
                player_total=pt,
                dealer_total=dt,
            )

    # ---------------- políticas de decisión ----------------

    def _should_player_hit(self, hand: Hand, dealer_up: Card) -> bool:
        if hand.is_blackjack or hand.is_bust:
            return False
        v = hand.value
        du = dealer_up.value
        if hand.is_soft:
            if v <= 17:
                return True
            if v == 18 and du >= 9:
                return True
            return False
        # mano dura
        return v < 17

    def _should_dealer_hit(self, hand: Hand) -> bool:
        v = hand.value
        if v < 17:
            return True
        if v == 17 and hand.is_soft and not self.stand_on_soft_17:
            return True
        return False

    # ---------------- utilitario ----------------

    def parse_card(self, card_str: str) -> Card:
        s = card_str.strip().upper()
        if len(s) == 3 and s.startswith("10"):
            rank = "T"
            suit = s[2]
        elif len(s) == 2:
            rank, suit = s
        else:
            raise ValueError(f"Invalid card string: {card_str}")
        return Card(rank=rank, suit=suit)

