#!/usr/bin/env python3
import sys
from pathlib import Path
from typing import Dict

sys.path.append(str(Path(__file__).parent))

from utils.contratos import Event, EventType, Card
from m2_cerebro.contador import CardCounter
from m2_cerebro.estado_juego import GameState
from m3_decision.orquestador import DecisionOrchestrator
from m3_decision.gestion_riesgo import RiskState
from simulador.simulador_m1 import M1Simulator


class BlackjackSystem:
    def __init__(
        self,
        initial_bankroll: float = 10000,
        counting_system: str = "hilo",
        rounds: int = 1000,
        penetration: float = 0.75,
        verbose: bool = False,
        config_path: str = "configs/decision.json",
    ):
        self.verbose = verbose
        self.counting_system = counting_system.lower()
        self.penetration = penetration
        self.config_path = config_path

        self.counter = CardCounter(system=self.counting_system)
        self.game_state = GameState()
        self.decision_maker = DecisionOrchestrator(
            initial_bankroll=initial_bankroll,
            config_path=config_path,
        )
        self.m1_sim = M1Simulator(max_rounds=rounds)

    def _parse_card(self, card_str: str) -> Card:
        rank = card_str[:-1]
        suit = card_str[-1]
        return Card(rank, suit)

    def process_event(self, event: Event) -> None:
        data = event.data or {}

        if event.event_type == EventType.ROUND_START:
            round_id = event.round_id or data.get('round_id', 'unknown')
            self.game_state.start_round(round_id)
            snapshot = self.counter.get_snapshot()
            self.decision_maker.process_count_update(snapshot)
            self.decision_maker.decide_bet()

        elif event.event_type == EventType.CARD_DEALT_SHARED:
            for card_str in data.get('cards', []):
                if not card_str:
                    continue
                card = self._parse_card(card_str)
                self.counter.process_card(card)
                self.game_state.add_shared_card(card)
            self.counter.snapshot_pre()

        elif event.event_type == EventType.CARD_DEALT:
            card_str = data.get('card')
            if not card_str:
                return
            card = self._parse_card(card_str)
            self.counter.process_card(card)

            who = data.get('who', '')
            if who.startswith('dealer'):
                self.game_state.add_dealer_card(card)
                self.counter.snapshot_mid()

        elif event.event_type == EventType.STATE_TEXT:
            text = data.get('text', '')
            if self.verbose and text:
                print(f"ℹ️  {text}")
            if text and 'shuffling' in text.lower():
                self.counter.reset()
                self.decision_maker.process_count_update(self.counter.get_snapshot())

        elif event.event_type == EventType.ROUND_END:
            result = data.get('result')
            amount = data.get('amount', 0)
            self.game_state.record_result(result)
            if result == 'win':
                self.decision_maker.update_result(True, amount)
            elif result == 'loss':
                self.decision_maker.update_result(False, amount)
            self.counter.snapshot_post()

    def run(self) -> Dict:
        print(f"🚀 Iniciando simulación con sistema: {self.counting_system.upper()}...")
        for event in self.m1_sim.generate_events():
            self.process_event(event)
            risk_state, risk_msg, _ = self.decision_maker.risk_manager.evaluate_risk()
            if risk_state == RiskState.STOPPED:
                stop_message = risk_msg or "Gestión de riesgo detuvo la simulación."
                print(f"🛑 SIMULACIÓN DETENIDA: {stop_message}")
                break

        print("✅ Simulación completada.")
        return self.decision_maker.get_status()


def print_summary(title: str, results: Dict) -> None:
    print("\n" + "=" * 60)
    print(f"📊 RESUMEN FINAL DE SESIÓN: {title.upper()}")
    print("=" * 60)
    print(f"   Bankroll final: ${results['bankroll']:,.2f}")
    print(f"   P&L Total: ${results['session_pnl']:+,.2f} ({results['session_pnl_pct']:+.2%})")
    print(f"   Bankroll máximo: ${results['peak_bankroll']:,.2f}")
    print(f"   Drawdown máximo: {results['drawdown']:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Sistema de Simulación Comparativa de Blackjack',
    )
    parser.add_argument(
        'bankroll',
        nargs='?',
        type=float,
        default=10000,
        help='Bankroll inicial',
    )
    parser.add_argument(
        '--rounds',
        type=int,
        default=1000,
        help='Número de rondas por simulación (default: 1000)',
    )
    parser.add_argument(
        '--penetration',
        type=float,
        default=0.75,
        help='Penetración del zapato (0-1, default: 0.75)',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Muestra mensajes adicionales durante la simulación',
    )
    args = parser.parse_args()

    # --- Simulación 1: Hi-Lo ---
    hilo_system = BlackjackSystem(
        initial_bankroll=args.bankroll,
        counting_system="hilo",
        rounds=args.rounds,
        penetration=args.penetration,
        verbose=args.verbose,
    )
    hilo_results = hilo_system.run()

    # --- Simulación 2: Zen ---
    zen_system = BlackjackSystem(
        initial_bankroll=args.bankroll,
        counting_system="zen",
        rounds=args.rounds,
        penetration=args.penetration,
        verbose=args.verbose,
    )
    zen_results = zen_system.run()

    # --- Resultados Comparativos ---
    print_summary("Hi-Lo", hilo_results)
    print_summary("Zen", zen_results)
