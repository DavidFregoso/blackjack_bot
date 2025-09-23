from typing import Dict, Tuple, Optional
from m3_decision.politica_jugada import PlayPolicy
from m3_decision.politica_apuesta import BetPolicy
from m3_decision.gestion_riesgo import RiskManager, RiskState
from utils.contratos import PlayAction, Event, EventType

class DecisionOrchestrator:
    """
    Orquestador principal del Módulo 3
    Coordina política de juego, apuestas y gestión de riesgo
    """
    
    def __init__(self, initial_bankroll: float = 10000):
        self.play_policy = PlayPolicy()
        self.bet_policy = BetPolicy()
        self.risk_manager = RiskManager()
        
        self.risk_manager.initialize(initial_bankroll)
        
        self.current_tc = 0.0
        self.next_bet = 0.0
        self.rounds_played = 0
        self.rounds_won = 0
        self.rounds_lost = 0
        
    def process_count_update(self, tc_snapshot: Dict):
        """Procesa actualización de conteo desde M2"""
        self.current_tc = tc_snapshot.get('tc_pre', 0.0)
    
    def decide_play(self, hand_value: int, is_soft: bool, 
                   dealer_up: int, can_double: bool = True, 
                   can_split: bool = False) -> Dict:
        """
        Decide la jugada óptima
        
        Args:
            hand_value: Valor de la mano del jugador
            is_soft: Si la mano es soft (con As)
            dealer_up: Carta visible del dealer
            can_double: Si se puede doblar
            can_split: Si se puede dividir
        
        Returns:
            Dict con acción, razón, TC usado y confianza
        """
        
        # Verificar estado de riesgo
        risk_state, risk_msg, risk_factor = self.risk_manager.evaluate_risk()
        
        if risk_state == RiskState.STOPPED:
            return {
                'action': PlayAction.STAND,
                'reason': f"Session Stopped: {risk_msg}",
                'tc_used': self.current_tc,
                'confidence': 0.0
            }
        
        # Obtener decisión de estrategia
        action, reason = self.play_policy.get_decision(
            hand_value, is_soft, dealer_up, 
            self.current_tc, can_double, can_split
        )
        
        # Calcular confianza basada en TC y estado de riesgo
        confidence = self.calculate_confidence(self.current_tc, risk_state)
        
        return {
            'action': action,
            'reason': reason,
            'tc_used': self.current_tc,
            'confidence': confidence
        }
    
    def decide_bet(self, tc_post: float = None) -> Dict:
        """
        Decide la apuesta para la próxima ronda
        
        Args:
            tc_post: TC después del dealer (opcional)
        
        Returns:
            Dict con unidades, monto, razón y estado
        """
        
        if tc_post is not None:
            self.current_tc = tc_post
        
        # Verificar estado de riesgo
        risk_state, risk_msg, risk_factor = self.risk_manager.evaluate_risk()
        
        if risk_state in [RiskState.STOPPED, RiskState.COOLDOWN]:
            return {
                'units': 0,
                'amount': 0,
                'rationale': risk_msg,
                'risk_state': risk_state.value,
                'should_sit': True
            }
        
        # Verificar si debemos sentarnos por TC bajo
        if self.bet_policy.should_sit_out(self.current_tc):
            return {
                'units': 0,
                'amount': 0,
                'rationale': f"TC too low: {self.current_tc:.2f}",
                'risk_state': risk_state.value,
                'should_sit': True
            }
        
        # Calcular apuesta
        bet_amount, rationale = self.bet_policy.calculate_bet(
            self.current_tc,
            self.risk_manager.current_bankroll,
            risk_factor
        )
        
        units = bet_amount / self.bet_policy.base_unit if self.bet_policy.base_unit > 0 else 0
        
        return {
            'units': units,
            'amount': bet_amount,
            'rationale': rationale,
            'risk_state': risk_state.value,
            'should_sit': False
        }
    
    def update_result(self, won: bool, amount: float):
        """
        Actualiza resultado de una ronda
        
        Args:
            won: Si se ganó la ronda
            amount: Monto ganado/perdido
        """
        
        self.rounds_played += 1
        
        if won:
            self.rounds_won += 1
            new_bankroll = self.risk_manager.current_bankroll + amount
        else:
            self.rounds_lost += 1
            new_bankroll = self.risk_manager.current_bankroll - amount
        
        self.risk_manager.update_bankroll(new_bankroll)
    
    def calculate_confidence(self, tc: float, risk_state: RiskState) -> float:
        """
        Calcula confianza en la decisión
        
        Args:
            tc: True Count actual
            risk_state: Estado de riesgo
        
        Returns:
            Confianza de 0.0 a 1.0
        """
        
        # Base confidence en TC
        if tc >= 3:
            base_confidence = 0.95
        elif tc >= 2:
            base_confidence = 0.90
        elif tc >= 1:
            base_confidence = 0.85
        elif tc >= 0:
            base_confidence = 0.80
        else:
            base_confidence = 0.70
        
        # Ajustar por estado de riesgo
        if risk_state == RiskState.WARNING:
            base_confidence *= 0.8
        elif risk_state == RiskState.COOLDOWN:
            base_confidence *= 0.5
        elif risk_state == RiskState.STOPPED:
            base_confidence = 0.0
        
        return base_confidence
    
    def get_status(self) -> Dict:
        """Retorna estado completo del orquestador"""
        status = self.risk_manager.get_status()
        
        win_rate = 0
        if self.rounds_played > 0:
            win_rate = self.rounds_won / self.rounds_played
        
        status.update({
            'current_tc': self.current_tc,
            'next_bet': self.next_bet,
            'rounds_played': self.rounds_played,
            'rounds_won': self.rounds_won,
            'rounds_lost': self.rounds_lost,
            'win_rate': win_rate
        })
        
        return status