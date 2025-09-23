import random
from typing import Generator, Optional

from utils.contratos import Event, EventType, Card, Hand


class Deck:
    """Representa uno o más mazos de cartas estándar."""

    def __init__(self, num_decks: int = 8):
        self.num_decks = num_decks
        self.cards = []
        ranks = [str(n) for n in range(2, 10)] + ['T', 'J', 'Q', 'K', 'A']
        suits = ['H', 'D', 'C', 'S']

        for _ in range(num_decks):
            for suit in suits:
                for rank in ranks:
                    self.cards.append(Card(rank, suit))

        self.shuffle()

    def shuffle(self) -> None:
        random.shuffle(self.cards)

    def deal(self) -> Optional[Card]:
        if not self.cards:
            return None
        return self.cards.pop()


class M1Simulator:
    """Simulador dinámico que reproduce rondas de blackjack."""

    def __init__(
        self,
        num_decks: int = 8,
        penetration: float = 0.75,
        max_rounds: Optional[int] = 1000,
    ):
        self.num_decks = num_decks
        self.penetration = max(0.0, min(penetration, 1.0))
        self.max_rounds = max_rounds

        self.deck = Deck(self.num_decks)
        total_cards = self.num_decks * 52
        penetration_cards = max(1, min(total_cards, int(total_cards * self.penetration)))
        self.shuffle_threshold = max(0, total_cards - penetration_cards)

        self.round_id_counter = 0

    def _need_shuffle(self) -> bool:
        return len(self.deck.cards) <= self.shuffle_threshold

    def _reshuffle(self) -> None:
        self.deck = Deck(self.num_decks)

    def generate_events(self) -> Generator[Event, None, None]:
        """Genera eventos de juego hasta alcanzar el límite configurado."""

        while self.max_rounds is None or self.round_id_counter < self.max_rounds:
            if self._need_shuffle():
                if self.max_rounds is not None and self.round_id_counter >= self.max_rounds:
                    break

                yield Event.create(
                    EventType.STATE_TEXT,
                    data={'text': 'Cutting card reached, shuffling...'},
                )
                self._reshuffle()
                continue

            if len(self.deck.cards) < 4:
                yield Event.create(
                    EventType.STATE_TEXT,
                    data={'text': 'Not enough cards to continue, reshuffling...'},
                )
                self._reshuffle()
                continue

            self.round_id_counter += 1
            round_id = f"sim_{self.round_id_counter}"

            yield Event.create(EventType.ROUND_START, round_id=round_id)

            player_hand = Hand([])
            dealer_hand = Hand([])

            # Reparto inicial
            first_player_card = self.deck.deal()
            dealer_up_card = self.deck.deal()
            second_player_card = self.deck.deal()
            dealer_hole_card = self.deck.deal()

            if None in [first_player_card, dealer_up_card, second_player_card, dealer_hole_card]:
                yield Event.create(
                    EventType.STATE_TEXT,
                    data={'text': 'Incomplete round due to depleted deck, reshuffling...'},
                )
                self._reshuffle()
                continue

            player_hand.add_card(first_player_card)
            player_hand.add_card(second_player_card)
            dealer_hand.add_card(dealer_up_card)
            dealer_hand.add_card(dealer_hole_card)

            yield Event.create(
                EventType.CARD_DEALT_SHARED,
                round_id=round_id,
                cards=[str(card) for card in player_hand.cards],
            )
            yield Event.create(
                EventType.CARD_DEALT,
                round_id=round_id,
                card=str(dealer_up_card),
                who='dealer_up',
            )

            # Turno del dealer
            while dealer_hand.value < 17:
                extra_card = self.deck.deal()
                if extra_card is None:
                    yield Event.create(
                        EventType.STATE_TEXT,
                        data={'text': 'Deck exhausted mid-round, reshuffling...'},
                    )
                    self._reshuffle()
                    break

                dealer_hand.add_card(extra_card)
                yield Event.create(
                    EventType.CARD_DEALT,
                    round_id=round_id,
                    card=str(extra_card),
                    who='dealer_draw',
                )
            else:
                player_value = player_hand.value
                dealer_value = dealer_hand.value

                result = 'push'
                if player_value > 21:
                    result = 'loss'
                elif dealer_value > 21:
                    result = 'win'
                elif player_value > dealer_value:
                    result = 'win'
                elif dealer_value > player_value:
                    result = 'loss'

                yield Event.create(
                    EventType.ROUND_END,
                    round_id=round_id,
                    result=result,
                    amount=25,
                )

                if self._need_shuffle():
                    if self.max_rounds is not None and self.round_id_counter >= self.max_rounds:
                        break

                    yield Event.create(
                        EventType.STATE_TEXT,
                        data={'text': 'Cutting card reached, shuffling...'},
                    )
                    self._reshuffle()

