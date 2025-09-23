import json
import random
import time
from pathlib import Path
from typing import Dict, Generator, List, Optional

from utils.contratos import Card, Event, EventType, Hand


class M1Simulator:
    """Simulador de M1 que genera rondas completas en tiempo real."""

    def __init__(
        self,
        config_path: str = "configs/settings.json",
        base_bet: float = 25.0,
        event_delay: float = 0.2,
    ):
        self.config = self._load_config(config_path)
        rules = self.config.get("rules", {})

        self.decks = int(rules.get("decks", 6))
        self.blackjack_payout = float(rules.get("blackjack_payout", 1.5))
        self.stand_on_soft_17 = bool(rules.get("s17", True))

        self.base_bet = base_bet
        self.event_delay = event_delay

        self.random = random.Random()
        self.round_counter = 0

        self.shoe: List[Card] = []
        self.cut_card_threshold = 0
        self.reset_shoe()

    def _load_config(self, config_path: str) -> Dict:
        path = Path(config_path)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        # Configuración por defecto si no existe archivo
        return {
            "rules": {
                "decks": 6,
                "s17": True,
                "blackjack_payout": 1.5,
            }
        }

    def reset_shoe(self):
        ranks = list("23456789TJQKA")
        suits = ["H", "D", "C", "S"]

        self.shoe = [
            Card(rank=rank, suit=suit)
            for _ in range(self.decks)
            for suit in suits
            for rank in ranks
        ]
        self.random.shuffle(self.shoe)

        # Barajar de nuevo cuando se alcance la carta de corte (20% del zapato restante)
        self.cut_card_threshold = max(int(len(self.shoe) * 0.2), 30)

    def needs_shuffle(self) -> bool:
        return len(self.shoe) <= self.cut_card_threshold

    def draw_card(self) -> Card:
        if not self.shoe:
            self.reset_shoe()
        return self.shoe.pop()

    def generate_events(self) -> Generator[Event, None, None]:
        while True:
            if self.needs_shuffle():
                self.reset_shoe()
                shuffle_event = self._create_event(
                    event_type=EventType.STATE_TEXT,
                    round_id=None,
                    data={"phase": "shuffle", "text": "Shuffling new shoe"},
                )
                yield shuffle_event
                time.sleep(self.event_delay)

            self.round_counter += 1
            round_id = f"sim_{self.round_counter:04d}"

            for event in self._play_round(round_id):
                yield event
                time.sleep(self.event_delay)

    def _play_round(self, round_id: str) -> Generator[Event, None, None]:
        player_hand = Hand(cards=[])
        dealer_hand = Hand(cards=[])

        yield self._create_event(
            event_type=EventType.ROUND_START,
            round_id=round_id,
            data={"round_id": round_id},
        )

        yield self._create_event(
            event_type=EventType.STATE_TEXT,
            round_id=round_id,
            data={"phase": "bets_open", "text": "Place your bets"},
        )

        yield self._create_event(
            event_type=EventType.STATE_TEXT,
            round_id=round_id,
            data={"phase": "dealing", "text": "Dealing cards"},
        )

        # Repartir cartas iniciales (jugador-jugador, crupier up, jugador, crupier hole)
        first_player_card = self.draw_card()
        dealer_up = self.draw_card()
        second_player_card = self.draw_card()
        dealer_hole = self.draw_card()

        player_hand.add_card(first_player_card)
        player_hand.add_card(second_player_card)
        dealer_hand.add_card(dealer_up)
        dealer_hand.add_card(dealer_hole)

        yield self._create_event(
            event_type=EventType.CARD_DEALT_SHARED,
            round_id=round_id,
            data={
                "cards": [str(first_player_card), str(second_player_card)],
                "who": "player_shared",
            },
        )

        yield self._create_event(
            event_type=EventType.CARD_DEALT,
            round_id=round_id,
            data={"card": str(dealer_up), "who": "dealer_up"},
        )

        # Blackjack natural
        if player_hand.is_blackjack:
            if dealer_hand.is_blackjack:
                yield self._create_event(
                    event_type=EventType.CARD_DEALT,
                    round_id=round_id,
                    data={"card": str(dealer_hole), "who": "dealer_hole_reveal"},
                )
                text = "Push: both have blackjack"
                result = "push"
                amount = 0.0
                reason = "push_blackjack"
            else:
                text = "Blackjack! Player wins"
                result = "win"
                amount = self.base_bet * self.blackjack_payout
                reason = "blackjack"

            yield self._create_event(
                event_type=EventType.STATE_TEXT,
                round_id=round_id,
                data={"phase": "payouts", "text": text},
            )

            yield self._create_event(
                event_type=EventType.ROUND_END,
                round_id=round_id,
                data={
                    "result": result,
                    "amount": round(amount, 2),
                    "reason": reason,
                    "player_total": player_hand.value,
                    "dealer_total": dealer_hand.value,
                },
            )
            return

        # Turno del jugador
        yield self._create_event(
            event_type=EventType.STATE_TEXT,
            round_id=round_id,
            data={"phase": "player_action", "text": "Your turn"},
        )

        while True:
            if player_hand.value >= 21:
                break

            if self._should_player_hit(player_hand, dealer_up):
                yield self._create_event(
                    event_type=EventType.MY_DECISION_LOCKED,
                    round_id=round_id,
                    data={
                        "action": "HIT",
                        "player_total": player_hand.value,
                        "dealer_up": str(dealer_up),
                    },
                )

                new_card = self.draw_card()
                player_hand.add_card(new_card)

                yield self._create_event(
                    event_type=EventType.CARD_DEALT_SHARED,
                    round_id=round_id,
                    data={"cards": [str(new_card)], "who": "player_shared"},
                )

                if player_hand.is_bust:
                    break
            else:
                yield self._create_event(
                    event_type=EventType.MY_DECISION_LOCKED,
                    round_id=round_id,
                    data={
                        "action": "STAND",
                        "player_total": player_hand.value,
                        "dealer_up": str(dealer_up),
                    },
                )
                break

        if player_hand.is_bust:
            yield self._create_event(
                event_type=EventType.STATE_TEXT,
                round_id=round_id,
                data={
                    "phase": "payouts",
                    "text": f"Player busts with {player_hand.value}",
                },
            )

            yield self._create_event(
                event_type=EventType.ROUND_END,
                round_id=round_id,
                data={
                    "result": "loss",
                    "amount": self.base_bet,
                    "reason": "player_bust",
                    "player_total": player_hand.value,
                    "dealer_total": dealer_hand.value,
                },
            )
            return

        # Otros jugadores (simulación sencilla)
        other_cards = self.random.randint(0, 3)
        if other_cards > 0:
            yield self._create_event(
                event_type=EventType.STATE_TEXT,
                round_id=round_id,
                data={"phase": "others_action", "text": "Others playing"},
            )

            for _ in range(other_cards):
                card = self.draw_card()
                yield self._create_event(
                    event_type=EventType.CARD_DEALT,
                    round_id=round_id,
                    data={"card": str(card), "who": "others_overlay"},
                )

        # Turno del crupier
        yield self._create_event(
            event_type=EventType.STATE_TEXT,
            round_id=round_id,
            data={"phase": "dealer_action", "text": "Dealer playing"},
        )

        yield self._create_event(
            event_type=EventType.CARD_DEALT,
            round_id=round_id,
            data={"card": str(dealer_hole), "who": "dealer_hole_reveal"},
        )

        while self._should_dealer_hit(dealer_hand):
            new_card = self.draw_card()
            dealer_hand.add_card(new_card)

            yield self._create_event(
                event_type=EventType.CARD_DEALT,
                round_id=round_id,
                data={"card": str(new_card), "who": "dealer_draw"},
            )

        dealer_bust = dealer_hand.is_bust
        player_total = player_hand.value
        dealer_total = dealer_hand.value

        if dealer_bust:
            text = "Dealer busts! Player wins"
            result = "win"
            amount = self.base_bet
            reason = "dealer_bust"
        elif dealer_total > player_total:
            text = f"Dealer has {dealer_total}, player has {player_total}"
            result = "loss"
            amount = self.base_bet
            reason = "dealer_wins"
        elif dealer_total < player_total:
            text = f"Player wins {player_total} vs {dealer_total}"
            result = "win"
            amount = self.base_bet
            reason = "player_wins"
        else:
            text = f"Push: {player_total} vs {dealer_total}"
            result = "push"
            amount = 0.0
            reason = "push"

        yield self._create_event(
            event_type=EventType.STATE_TEXT,
            round_id=round_id,
            data={"phase": "payouts", "text": text},
        )

        yield self._create_event(
            event_type=EventType.ROUND_END,
            round_id=round_id,
            data={
                "result": result,
                "amount": round(amount, 2),
                "reason": reason,
                "player_total": player_total,
                "dealer_total": dealer_total,
            },
        )

    def _should_player_hit(self, hand: Hand, dealer_up: Card) -> bool:
        if hand.is_blackjack or hand.is_bust:
            return False

        value = hand.value
        dealer_value = dealer_up.value

        if hand.is_soft:
            if value <= 17:
                return True
            if value == 18 and dealer_value >= 9:
                return True
            return False

        return value < 17

    def _should_dealer_hit(self, hand: Hand) -> bool:
        value = hand.value
        if value < 17:
            return True
        if value == 17 and hand.is_soft and not self.stand_on_soft_17:
            return True
        return False

    def _create_event(
        self,
        event_type: EventType,
        round_id: Optional[str],
        data: Optional[Dict] = None,
    ) -> Event:
        return Event(
            timestamp=time.time(),
            event_type=event_type,
            round_id=round_id,
            data=data or {},
        )

    def parse_card(self, card_str: str) -> Card:
        card_str = card_str.strip().upper()

        if len(card_str) == 3 and card_str.startswith("10"):
            rank = "T"
            suit = card_str[2]
        elif len(card_str) == 2:
            rank, suit = card_str
        else:
            raise ValueError(f"Invalid card string: {card_str}")

        return Card(rank=rank, suit=suit)
