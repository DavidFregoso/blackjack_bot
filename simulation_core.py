from utils.contratos import Event, EventType, Card
from m2_cerebro.contador import CardCounter
from m3_decision.orquestador import DecisionOrchestrator
from m3_decision.gestion_riesgo import RiskState
from simulador.simulador_m1 import M1Simulator


class BlackjackSystem:
    """El motor de simulación de Blackjack. Es reutilizable y no imprime nada."""

    def __init__(
        self,
        initial_bankroll: float,
        counting_system: str,
        stop_loss_pct: float,
        max_rounds: int | None = 1000,
    ):
        self.counter = CardCounter(system=counting_system)
        self.decision_maker = DecisionOrchestrator(initial_bankroll=initial_bankroll)
        self.decision_maker.risk_manager.stop_loss_pct = stop_loss_pct
        self.m1_sim = M1Simulator(max_rounds=max_rounds)
        self.bankroll_history = [initial_bankroll]

    def process_event(self, event: Event):
        if event.event_type == EventType.ROUND_END:
            data = event.data or {}
            result = data.get('result')
            amount = data.get('amount', 25)
            if result == 'win':
                self.decision_maker.update_result(True, amount)
            elif result == 'loss':
                self.decision_maker.update_result(False, amount)

            current_bankroll = self.decision_maker.risk_manager.current_bankroll
            self.bankroll_history.append(current_bankroll)

        elif event.event_type in {EventType.CARD_DEALT, EventType.CARD_DEALT_SHARED}:
            data = event.data or {}
            cards = data.get('cards') or [data.get('card')]
            for card_str in cards:
                if card_str:
                    rank, suit = card_str[:-1], card_str[-1:]
                    self.counter.process_card(Card(rank, suit))

        elif event.event_type == EventType.STATE_TEXT:
            text = (event.data or {}).get('text', '')
            if text and 'shuffling' in text.lower():
                self.counter.reset()

    def run(self):
        """Ejecuta una simulación completa y devuelve los resultados."""
        for event in self.m1_sim.generate_events():
            self.process_event(event)
            risk_state, _, _ = self.decision_maker.risk_manager.evaluate_risk()
            if risk_state == RiskState.STOPPED:
                break

        final_status = self.decision_maker.get_status()
        final_status['bankroll_history'] = self.bankroll_history
        return final_status
