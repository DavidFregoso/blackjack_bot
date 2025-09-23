from typing import Optional, Dict, List
from utils.contratos import GamePhase, Event, EventType

class GameFSM:
    """
    Máquina de Estados Finitos para el flujo del juego
    Gestiona las transiciones entre fases de forma consistente
    """
    
    def __init__(self):
        self.current_phase = GamePhase.IDLE
        self.phase_history = []
        self.phase_timestamps = {}
        self.transition_count = 0
        
        # Definir transiciones válidas
        self.transitions = {
            GamePhase.IDLE: [
                GamePhase.BETS_OPEN
            ],
            GamePhase.BETS_OPEN: [
                GamePhase.DEALING, 
                GamePhase.IDLE  # Si se cancela
            ],
            GamePhase.DEALING: [
                GamePhase.MY_ACTION,  # Normal
                GamePhase.PAYOUTS    # Si hay BJ inmediato
            ],
            GamePhase.MY_ACTION: [
                GamePhase.OTHERS_ACTIONS,  # Si hay otros jugadores
                GamePhase.DEALER_PLAY,     # Si no hay otros
                GamePhase.PAYOUTS          # Si todos se pasan
            ],
            GamePhase.OTHERS_ACTIONS: [
                GamePhase.DEALER_PLAY,
                GamePhase.PAYOUTS
            ],
            GamePhase.DEALER_PLAY: [
                GamePhase.PAYOUTS
            ],
            GamePhase.PAYOUTS: [
                GamePhase.IDLE,
                GamePhase.BETS_OPEN  # Nueva ronda inmediata
            ]
        }
        
        # Mapeo de texto a fase
        self.phase_map = {
            'bets_open': GamePhase.BETS_OPEN,
            'betting': GamePhase.BETS_OPEN,
            'place_bets': GamePhase.BETS_OPEN,
            'dealing': GamePhase.DEALING,
            'cards_dealt': GamePhase.DEALING,
            'player_action': GamePhase.MY_ACTION,
            'my_action': GamePhase.MY_ACTION,
            'your_turn': GamePhase.MY_ACTION,
            'others_action': GamePhase.OTHERS_ACTIONS,
            'others_actions': GamePhase.OTHERS_ACTIONS,
            'other_players': GamePhase.OTHERS_ACTIONS,
            'dealer_action': GamePhase.DEALER_PLAY,
            'dealer_play': GamePhase.DEALER_PLAY,
            'dealer_turn': GamePhase.DEALER_PLAY,
            'payouts': GamePhase.PAYOUTS,
            'results': GamePhase.PAYOUTS,
            'round_end': GamePhase.PAYOUTS,
            'idle': GamePhase.IDLE,
            'waiting': GamePhase.IDLE
        }
    
    def can_transition_to(self, new_phase: GamePhase) -> bool:
        """Verifica si una transición es válida"""
        return new_phase in self.transitions.get(self.current_phase, [])
    
    def transition(self, new_phase: GamePhase) -> bool:
        """
        Realiza una transición si es válida
        
        Args:
            new_phase: Nueva fase a transicionar
            
        Returns:
            True si la transición fue exitosa
        """
        if self.can_transition_to(new_phase):
            # Guardar en historial
            self.phase_history.append({
                'from': self.current_phase,
                'to': new_phase,
                'transition_number': self.transition_count
            })
            
            # Registrar timestamp
            import time
            self.phase_timestamps[new_phase] = time.time()
            
            # Actualizar fase
            self.current_phase = new_phase
            self.transition_count += 1
            
            # Mantener solo las últimas 20 transiciones
            if len(self.phase_history) > 20:
                self.phase_history.pop(0)
                
            return True
        else:
            # Log de transición inválida
            print(f"⚠️ Transición inválida: {self.current_phase.value} → {new_phase.value}")
            return False
    
    def process_event(self, event: Event) -> Optional[GamePhase]:
        """
        Procesa un evento y actualiza la fase si corresponde
        
        Args:
            event: Evento a procesar
            
        Returns:
            Nueva fase si hubo transición, None si no
        """
        if event.event_type == EventType.STATE_TEXT:
            # Extraer texto de fase
            phase_text = event.data.get('phase', '').lower().replace(' ', '_')
            
            # Buscar en mapeo
            new_phase = self.phase_map.get(phase_text)
            
            if new_phase and self.transition(new_phase):
                return new_phase
        
        elif event.event_type == EventType.ROUND_START:
            if self.transition(GamePhase.BETS_OPEN):
                return GamePhase.BETS_OPEN
        
        elif event.event_type == EventType.ROUND_END:
            if self.transition(GamePhase.IDLE):
                return GamePhase.IDLE
        
        elif event.event_type == EventType.CARD_DEALT_SHARED:
            # Si estamos en BETS_OPEN, pasar a DEALING
            if self.current_phase == GamePhase.BETS_OPEN:
                if self.transition(GamePhase.DEALING):
                    return GamePhase.DEALING
        
        elif event.event_type == EventType.MY_DECISION_LOCKED:
            # Si estamos en MY_ACTION, podemos avanzar
            if self.current_phase == GamePhase.MY_ACTION:
                # Por defecto, asumir que hay otros jugadores
                if self.transition(GamePhase.OTHERS_ACTIONS):
                    return GamePhase.OTHERS_ACTIONS
        
        return None
    
    def force_transition(self, new_phase: GamePhase) -> bool:
        """
        Fuerza una transición (solo para debugging)
        
        Args:
            new_phase: Fase a forzar
            
        Returns:
            True siempre
        """
        self.phase_history.append({
            'from': self.current_phase,
            'to': new_phase,
            'forced': True,
            'transition_number': self.transition_count
        })
        
        self.current_phase = new_phase
        self.transition_count += 1
        return True
    
    def get_state(self) -> Dict:
        """Retorna el estado actual de la FSM"""
        import time
        
        # Tiempo en fase actual
        time_in_phase = 0
        if self.current_phase in self.phase_timestamps:
            time_in_phase = time.time() - self.phase_timestamps[self.current_phase]
        
        return {
            'current_phase': self.current_phase.value,
            'valid_transitions': [
                phase.value for phase in self.transitions.get(self.current_phase, [])
            ],
            'transition_count': self.transition_count,
            'time_in_phase': time_in_phase,
            'last_transitions': [
                f"{t['from'].value}→{t['to'].value}" 
                for t in self.phase_history[-5:]
            ]
        }
    
    def reset(self):
        """Reinicia la FSM al estado inicial"""
        self.current_phase = GamePhase.IDLE
        self.phase_history = []
        self.phase_timestamps = {}
        self.transition_count = 0