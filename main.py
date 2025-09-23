import json
import time
import sys
from pathlib import Path

# Añadir el directorio raíz al path
sys.path.append(str(Path(__file__).parent))

from utils.contratos import Event, EventType, Card, Hand, GamePhase
from m2_cerebro.contador import CardCounter
from m2_cerebro.estado_juego import GameState
from m2_cerebro.fsm import GameFSM
from m3_decision.orquestador import DecisionOrchestrator
from simulador.simulador_m1 import M1Simulator

class BlackjackSystem:
    def __init__(self, initial_bankroll: float = 10000):
        print("🎰 Iniciando Sistema de Blackjack...")
        
        # Módulo 2: Cerebro
        self.counter = CardCounter()
        self.game_state = GameState()
        self.fsm = GameFSM()
        
        # Módulo 3: Decisión
        self.decision_maker = DecisionOrchestrator(initial_bankroll)
        
        # Simulador M1
        self.m1_sim = M1Simulator()
        
        print(f"✅ Sistema inicializado con bankroll: ${initial_bankroll}")
        print()
    
    def process_event(self, event: Event):
        
        print(f"📨 Evento: {event.event_type.value}", end="")
        if event.data:
            print(f" - {event.data}")
        else:
            print()
        
        # Procesar según tipo de evento
        if event.event_type == EventType.ROUND_START:
            self.handle_round_start(event)
        
        elif event.event_type == EventType.CARD_DEALT_SHARED:
            self.handle_shared_card(event)
        
        elif event.event_type == EventType.CARD_DEALT:
            self.handle_card_dealt(event)
        
        elif event.event_type == EventType.STATE_TEXT:
            self.handle_state_change(event)
        
        elif event.event_type == EventType.MY_DECISION_LOCKED:
            self.handle_decision_needed(event)
        
        elif event.event_type == EventType.ROUND_END:
            self.handle_round_end(event)
    
    def handle_round_start(self, event: Event):
        round_id = event.data.get('round_id', 'unknown')
        self.game_state.start_round(round_id)
        self.fsm.process_event(event)
        
        print(f"🎲 Nueva ronda: {round_id}")
        
        # Calcular apuesta para la próxima ronda
        bet_decision = self.decision_maker.decide_bet()
        print(f"💰 Apuesta recomendada: ${bet_decision['amount']:.2f} ({bet_decision['rationale']})")
        print()
    
    def handle_shared_card(self, event: Event):
        cards_data = event.data.get('cards', [])
        for card_str in cards_data:
            card = self.m1_sim.parse_card(card_str)
            self.counter.process_card(card)
            self.game_state.add_shared_card(card)
            print(f"  🃏 Carta compartida: {card}")
        
        # Snapshot TC_pre
        tc_pre = self.counter.snapshot_pre()
        print(f"  📊 TC_pre = {tc_pre:.2f}")
    
    def handle_card_dealt(self, event: Event):
        card_str = event.data.get('card')
        who = event.data.get('who')
        
        if card_str:
            card = self.m1_sim.parse_card(card_str)
            self.counter.process_card(card)
            
            if who == 'dealer_up':
                self.game_state.add_dealer_card(card)
                print(f"  🎰 Carta del dealer: {card}")
            elif who == 'others_overlay':
                self.game_state.add_others_card(card)
                print(f"  👥 Carta de otros: {card}")
                # Actualizar TC_mid
                tc_mid = self.counter.snapshot_mid()
                print(f"  📊 TC_mid = {tc_mid:.2f}")
            elif who == 'dealer_draw':
                self.game_state.add_dealer_card(card)
                print(f"  🎰 Dealer pide: {card}")
                # Actualizar TC_post
                tc_post = self.counter.snapshot_post()
                print(f"  📊 TC_post = {tc_post:.2f}")
    
    def handle_state_change(self, event: Event):
        phase_text = event.data.get('phase')
        new_phase = self.fsm.process_event(event)
        if new_phase:
            self.game_state.set_phase(new_phase)
            print(f"  🔄 Fase: {new_phase.value}")
    
    def handle_decision_needed(self, event: Event):
        print("\\n  🤔 Decisión requerida:")
        
        # Obtener estado actual
        state = self.game_state.get_state()
        
        # Tomar decisión
        decision = self.decision_maker.decide_play(
            hand_value=state['my_hand_value'],
            is_soft=state['my_hand_soft'],
            dealer_up=state['dealer_up_value']
        )
        
        print(f"  ✅ Acción: {decision['action'].value}")
        print(f"  📝 Razón: {decision['reason']}")
        print(f"  📊 TC usado: {decision['tc_used']:.2f}")
        print(f"  🎯 Confianza: {decision['confidence']:.1%}")
        print()
    
    def handle_round_end(self, event: Event):
        result = event.data.get('result', 'unknown')
        amount = event.data.get('amount', 0)
        
        print(f"\\n🏁 Fin de ronda")
        print(f"  Resultado: {result}")
        
        # Actualizar bankroll
        if result == 'win':
            self.decision_maker.update_result(True, amount)
            print(f"  ✅ Ganancia: ${amount:.2f}")
        elif result == 'loss':
            self.decision_maker.update_result(False, amount)
            print(f"  ❌ Pérdida: ${amount:.2f}")
        
        # Mostrar estado
        status = self.decision_maker.get_status()
        print(f"\\n  💼 Estado de la sesión:")
        print(f"     Bankroll: ${status['bankroll']:.2f}")
        print(f"     P&L: ${status['session_pnl']:.2f} ({status['session_pnl_pct']:.1%})")
        print(f"     Estado de riesgo: {status['state']}")
        print("=" * 60)
        print()
    
    def run(self):
        print("🚀 Ejecutando simulación...\\n")
        print("=" * 60)
        
        try:
            # Procesar eventos del simulador
            for event in self.m1_sim.generate_events():
                self.process_event(event)
                
                # Verificar si debemos parar
                status = self.decision_maker.get_status()
                if status['state'] == 'stopped':
                    print("\\n⛔ Sesión detenida por gestión de riesgo")
                    break
            
            print("\\n✅ Simulación completada")
            
            # Resumen final
            self.print_summary()
            
        except KeyboardInterrupt:
            print("\\n⚠️ Simulación interrumpida por usuario")
            self.print_summary()
        except Exception as e:
            print(f"\\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    def print_summary(self):
        print("\\n" + "=" * 60)
        print("📊 RESUMEN DE LA SESIÓN")
        print("=" * 60)
        
        # Estado del contador
        count_snapshot = self.counter.get_snapshot()
        print(f"Cartas vistas: {count_snapshot['cards_seen']}")
        print(f"RC (Hi-Lo): {count_snapshot['rc_hilo']}")
        print(f"RC (Zen): {count_snapshot['rc_zen']}")
        print(f"Mazos restantes: {count_snapshot['decks_remaining']:.2f}")
        
        print()
        
        # Estado financiero
        status = self.decision_maker.get_status()
        print(f"Bankroll inicial: ${10000:.2f}")
        print(f"Bankroll final: ${status['bankroll']:.2f}")
        print(f"P&L: ${status['session_pnl']:.2f} ({status['session_pnl_pct']:.1%})")
        print(f"Peak bankroll: ${status['peak_bankroll']:.2f}")
        print(f"Drawdown: {status['drawdown']:.1%}")
        print(f"Tiempo de sesión: {status['session_time']/60:.1f} minutos")
        print("=" * 60)

if __name__ == "__main__":
    # Crear y ejecutar el sistema
    system = BlackjackSystem(initial_bankroll=10000)
    system.run()