#!/usr/bin/env python3
import json
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from utils.contratos import Event, EventType, Card, Hand, GamePhase
from m2_cerebro.contador import CardCounter
from m2_cerebro.estado_juego import GameState
from m2_cerebro.fsm import GameFSM
from m3_decision.orquestador import DecisionOrchestrator
from simulador.simulador_m1 import M1Simulator

class BlackjackSystem:
    def __init__(self, initial_bankroll: float = 10000, verbose: bool = True):
        self.verbose = verbose
        print("🎰 Iniciando Sistema de Blackjack...")
        print("=" * 60)
        
        # Módulos
        self.counter = CardCounter()
        self.game_state = GameState()
        self.fsm = GameFSM()
        self.decision_maker = DecisionOrchestrator(initial_bankroll)
        self.m1_sim = M1Simulator()
        
        print(f"💰 Bankroll inicial: ${initial_bankroll:,.2f}")
        print(f"📊 Sistema: Hi-Lo con 18 índices")
        print(f"🎯 Modo: {'Detallado' if verbose else 'Resumido'}")
        print("=" * 60)
        print()
    
    def process_event(self, event: Event):
        if self.verbose:
            self.log_event(event)
        
        # Procesar según tipo
        handlers = {
            EventType.ROUND_START: self.handle_round_start,
            EventType.CARD_DEALT_SHARED: self.handle_shared_card,
            EventType.CARD_DEALT: self.handle_card_dealt,
            EventType.STATE_TEXT: self.handle_state_change,
            EventType.MY_DECISION_LOCKED: self.handle_decision_needed,
            EventType.ROUND_END: self.handle_round_end
        }
        
        handler = handlers.get(event.event_type)
        if handler:
            handler(event)
    
    def log_event(self, event: Event):
        if not self.verbose:
            return
            
        icons = {
            EventType.ROUND_START: "🎲",
            EventType.ROUND_END: "🏁",
            EventType.CARD_DEALT_SHARED: "🃏",
            EventType.CARD_DEALT: "🎴",
            EventType.STATE_TEXT: "📝",
            EventType.MY_DECISION_LOCKED: "🤔"
        }
        
        icon = icons.get(event.event_type, "📨")
        print(f"{icon} {event.event_type.value}: {event.data or ''}")
    
    def handle_round_start(self, event: Event):
        round_id = event.data.get('round_id', 'unknown')
        self.game_state.start_round(round_id)
        self.fsm.process_event(event)
        
        print(f"\n{'='*60}")
        print(f"🎲 RONDA #{self.game_state.round_count}: {round_id}")
        print(f"{'='*60}")
        
        # Snapshot actual
        count_snapshot = self.counter.get_snapshot()
        self.decision_maker.process_count_update(count_snapshot)
        
        # Decisión de apuesta
        bet_decision = self.decision_maker.decide_bet()
        
        print(f"📊 Conteo: RC={count_snapshot['rc_hilo']:+d}, TC={count_snapshot['tc_current']:.2f}")
        print(f"💰 Apuesta: ${bet_decision['amount']:.2f} ({bet_decision['units']:.1f} unidades)")
        if bet_decision['should_sit']:
            print(f"   ⚠️ {bet_decision['rationale']}")
    
    def handle_shared_card(self, event: Event):
        cards_data = event.data.get('cards', [])
        print(f"\n🎯 Mis cartas:")
        
        for card_str in cards_data:
            card = self.m1_sim.parse_card(card_str)
            self.counter.process_card(card)
            self.game_state.add_shared_card(card)
            print(f"   {self.get_card_display(card)}")
        
        tc_pre = self.counter.snapshot_pre()
        hand_desc = self.game_state.get_hand_description()
        print(f"   → {hand_desc} | TC={tc_pre:.2f}")
    
    def handle_card_dealt(self, event: Event):
        card_str = event.data.get('card')
        who = event.data.get('who')
        
        if not card_str:
            return
            
        card = self.m1_sim.parse_card(card_str)
        self.counter.process_card(card)
        
        displays = {
            'dealer_up': ('🎰 Dealer muestra:', self.game_state.add_dealer_card),
            'dealer_hole_reveal': ('🎰 Carta oculta:', self.game_state.add_dealer_card),
            'dealer_draw': ('🎰 Dealer pide:', self.game_state.add_dealer_card),
            'others_overlay': ('👥 Otros jugadores:', self.game_state.add_others_card)
        }
        
        if who in displays:
            label, add_func = displays[who]
            add_func(card)
            print(f"{label} {self.get_card_display(card)}")
            
            if who == 'others_overlay':
                self.counter.snapshot_mid()
            elif who in ['dealer_draw', 'dealer_hole_reveal']:
                tc_post = self.counter.snapshot_post()
                if who == 'dealer_draw':
                    print(f"   TC posterior: {tc_post:.2f}")
    
    def handle_state_change(self, event: Event):
        new_phase = self.fsm.process_event(event)
        if new_phase:
            self.game_state.set_phase(new_phase)
            if self.verbose:
                print(f"→ Fase: {new_phase.value}")
    
    def handle_decision_needed(self, event: Event):
        print("\n" + "─" * 40)
        print("💭 DECISIÓN REQUERIDA")
        print("─" * 40)
        
        state = self.game_state.get_state()
        count_snapshot = self.counter.get_snapshot()
        self.decision_maker.process_count_update(count_snapshot)
        
        decision = self.decision_maker.decide_play(
            hand_value=state['my_hand_value'],
            is_soft=state['my_hand_soft'],
            dealer_up=state['dealer_up_value']
        )
        
        print(f"Mi mano: {state['my_hand_value']} {'SOFT' if state['my_hand_soft'] else 'HARD'}")
        print(f"Dealer: {state['dealer_up_value']}")
        print(f"TC: {decision['tc_used']:.2f}")
        print(f"\n✅ ACCIÓN: {decision['action'].value}")
        print(f"📋 Razón: {decision['reason']}")
        print(f"🎯 Confianza: {decision['confidence']:.0%}")
        print("─" * 40)
    
    def handle_round_end(self, event: Event):
        result = event.data.get('result', 'unknown')
        amount = event.data.get('amount', 0)
        
        # Actualizar resultado
        self.game_state.record_result(result)
        
        print(f"\n{'='*40}")
        print("🏁 RESULTADO")
        print(f"{'='*40}")
        
        result_display = {
            'win': ('✅ GANASTE', f"+${amount:.2f}"),
            'loss': ('❌ PERDISTE', f"-${amount:.2f}"),
            'push': ('🤝 EMPATE', "$0.00")
        }
        
        if result in result_display:
            label, money = result_display[result]
            print(f"{label}: {money}")
            
            if result == 'win':
                self.decision_maker.update_result(True, amount)
            elif result == 'loss':
                self.decision_maker.update_result(False, amount)
        
        # Estado actualizado
        status = self.decision_maker.get_status()
        print(f"\n💼 Bankroll: ${status['bankroll']:,.2f}")
        print(f"📈 Sesión: ${status['session_pnl']:+.2f} ({status['session_pnl_pct']:+.1%})")
        
        if status['state'] != 'normal':
            print(f"⚠️ Estado: {status['state'].upper()}")
    
    def get_card_display(self, card: Card) -> str:
        """Muestra carta con símbolo y color"""
        suits = {'H': '♥️', 'D': '♦️', 'C': '♣️', 'S': '♠️'}
        colors = {'H': '\033[91m', 'D': '\033[91m', 'C': '\033[90m', 'S': '\033[90m'}
        reset = '\033[0m'
        
        suit = suits.get(card.suit, card.suit)
        color = colors.get(card.suit, '')
        return f"{color}{card.rank}{suit}{reset}"
    
    def run(self, max_rounds: int = None):
        print("\n🚀 INICIANDO SIMULACIÓN\n")
        
        rounds_played = 0
        try:
            for event in self.m1_sim.generate_events():
                self.process_event(event)
                
                if event.event_type == EventType.ROUND_END:
                    rounds_played += 1
                    
                    if max_rounds and rounds_played >= max_rounds:
                        print("\n📊 Límite de rondas alcanzado")
                        break
                
                status = self.decision_maker.get_status()
                if status['state'] == 'stopped':
                    print("\n🛑 SESIÓN DETENIDA - Gestión de Riesgo")
                    break
            
            self.print_final_summary()
            
        except KeyboardInterrupt:
            print("\n⚠️ Simulación interrumpida")
            self.print_final_summary()
    
    def print_final_summary(self):
        print("\n" + "="*60)
        print("📊 RESUMEN FINAL DE SESIÓN")
        print("="*60)
        
        # Conteo
        count = self.counter.get_snapshot()
        print(f"\n🎯 CONTEO FINAL:")
        print(f"   Cartas vistas: {count['cards_seen']}/{self.counter.total_cards}")
        print(f"   Penetración: {count['penetration']:.1%}")
        print(f"   RC Hi-Lo: {count['rc_hilo']:+d}")
        print(f"   TC Final: {count['tc_current']:.2f}")
        
        # Resultados
        status = self.decision_maker.get_status()
        game_stats = self.game_state.get_state()['stats']
        
        print(f"\n💰 RESULTADOS FINANCIEROS:")
        print(f"   Bankroll inicial: ${self.decision_maker.risk_manager.initial_bankroll:,.2f}")
        print(f"   Bankroll final: ${status['bankroll']:,.2f}")
        print(f"   P&L Total: ${status['session_pnl']:+,.2f} ({status['session_pnl_pct']:+.1%})")
        print(f"   Bankroll máximo: ${status['peak_bankroll']:,.2f}")
        print(f"   Drawdown máximo: {status['drawdown']:.1%}")
        
        print(f"\n🎮 ESTADÍSTICAS DE JUEGO:")
        print(f"   Rondas: {self.game_state.round_count}")
        print(f"   Manos ganadas: {game_stats['hands_won']}")
        print(f"   Manos perdidas: {game_stats['hands_lost']}")
        print(f"   Win rate: {game_stats['win_rate']:.1%}")
        print(f"   Blackjacks: {self.game_state.blackjacks}")
        
        print(f"\n⏱️ Duración: {status['session_time']/60:.1f} minutos")
        print("="*60)

if __name__ == "__main__":
    # Parsear argumentos
    import argparse
    parser = argparse.ArgumentParser(description='Sistema de Análisis de Blackjack')
    parser.add_argument('bankroll', nargs='?', type=float, default=10000,
                       help='Bankroll inicial (default: 10000)')
    parser.add_argument('--rounds', type=int, help='Número máximo de rondas')
    parser.add_argument('--quiet', action='store_true', help='Modo silencioso')
    
    args = parser.parse_args()
    
    # Crear y ejecutar sistema
    system = BlackjackSystem(
        initial_bankroll=args.bankroll,
        verbose=not args.quiet
    )
    system.run(max_rounds=args.rounds)