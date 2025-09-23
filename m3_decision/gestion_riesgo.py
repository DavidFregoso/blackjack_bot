import json
import time
from typing import Dict, Tuple, Optional
from enum import Enum
from pathlib import Path

class RiskState(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    COOLDOWN = "cooldown"
    STOPPED = "stopped"

class RiskManager:
    """
    Gestión de riesgo y bankroll
    Implementa stops, cooldowns y control de drawdown
    """
    
    def __init__(self, config_path: str = "configs/decision.json"):
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = self.get_default_config()
        
        self.risk_config = self.config.get('risk', {})
        
        # Límites
        self.stop_loss_abs = self.risk_config.get('stop_loss_abs', 1000)
        self.stop_loss_pct = self.risk_config.get('stop_loss_pct', 0.5)
        self.stop_win_abs = self.risk_config.get('stop_win_abs', 2000)
        self.stop_win_pct = self.risk_config.get('stop_win_pct', 2.0)
        self.max_drawdown_pct = self.risk_config.get('max_drawdown_pct', 0.3)
        
        # Estado
        self.initial_bankroll = 0
        self.current_bankroll = 0
        self.peak_bankroll = 0
        self.session_pnl = 0
        self.state = RiskState.NORMAL
        self.cooldown_until = 0
        self.session_start_time = time.time()
        self.consecutive_losses = 0
        self.consecutive_wins = 0
    
    def get_default_config(self):
        """Configuración por defecto"""
        return {
            'risk': {
                'stop_loss_abs': 1000,
                'stop_loss_pct': 0.5,
                'stop_win_abs': 2000,
                'stop_win_pct': 1.0,
                'max_drawdown_pct': 0.3
            }
        }
    
    def initialize(self, bankroll: float):
        """Inicializa el gestor con bankroll inicial"""
        self.initial_bankroll = bankroll
        self.current_bankroll = bankroll
        self.peak_bankroll = bankroll
        self.session_pnl = 0
        self.state = RiskState.NORMAL
        self.consecutive_losses = 0
        self.consecutive_wins = 0
    
    def update_bankroll(self, new_bankroll: float):
        """Actualiza bankroll y estadísticas"""
        # Detectar win/loss
        if new_bankroll > self.current_bankroll:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif new_bankroll < self.current_bankroll:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        
        self.current_bankroll = new_bankroll
        self.session_pnl = new_bankroll - self.initial_bankroll
        
        if new_bankroll > self.peak_bankroll:
            self.peak_bankroll = new_bankroll
    
    def evaluate_risk(self) -> Tuple[RiskState, Optional[str], float]:
        """
        Evalúa el estado de riesgo actual
        
        Returns:
            Tuple de (estado, mensaje, factor_de_riesgo)
            factor_de_riesgo: 0.0 = parar, 1.0 = normal
        """
        
        # Verificar cooldown
        if self.state == RiskState.COOLDOWN:
            if time.time() < self.cooldown_until:
                remaining = self.cooldown_until - time.time()
                return RiskState.COOLDOWN, f"Cooldown: {remaining:.0f}s remaining", 0.0
            else:
                self.state = RiskState.NORMAL
        
        # Stop Loss absoluto
        if self.session_pnl <= -self.stop_loss_abs:
            self.state = RiskState.STOPPED
            return RiskState.STOPPED, f"Stop Loss Hit: ${self.session_pnl:.2f}", 0.0
        
        # Stop Loss porcentual
        loss_pct = -self.session_pnl / self.initial_bankroll if self.initial_bankroll > 0 else 0
        if self.session_pnl < 0 and loss_pct >= self.stop_loss_pct:
            self.state = RiskState.STOPPED
            return RiskState.STOPPED, f"Stop Loss %: {loss_pct:.1%}", 0.0
        
        # Stop Win absoluto
        if self.session_pnl >= self.stop_win_abs:
            self.state = RiskState.STOPPED
            return RiskState.STOPPED, f"Stop Win Hit: ${self.session_pnl:.2f}", 0.0
        
        # Stop Win porcentual
        win_pct = self.session_pnl / self.initial_bankroll if self.initial_bankroll > 0 else 0
        if self.session_pnl > 0 and win_pct >= self.stop_win_pct:
            self.state = RiskState.STOPPED
            return RiskState.STOPPED, f"Stop Win %: {win_pct:.1%}", 0.0
        
        # Drawdown
        if self.peak_bankroll > 0:
            drawdown = (self.peak_bankroll - self.current_bankroll) / self.peak_bankroll
            if drawdown >= self.max_drawdown_pct:
                self.state = RiskState.WARNING
                return RiskState.WARNING, f"Max Drawdown: {drawdown:.1%}", 0.5
        
        # Rachas de pérdidas
        max_consecutive_losses = self.risk_config.get('max_consecutive_losses', 5)
        if self.consecutive_losses >= max_consecutive_losses:
            self.trigger_cooldown(60)  # Cooldown de 1 minuto
            return RiskState.COOLDOWN, f"Too many losses: {self.consecutive_losses}", 0.0
        
        # Warning zone (70% hacia stop loss)
        if self.session_pnl < 0 and loss_pct >= self.stop_loss_pct * 0.7:
            self.state = RiskState.WARNING
            return RiskState.WARNING, f"Approaching Stop Loss: {loss_pct:.1%}", 0.7
        
        # Normal
        self.state = RiskState.NORMAL
        return RiskState.NORMAL, None, 1.0
    
    def trigger_cooldown(self, seconds: int = 300):
        """Activa período de cooldown"""
        self.state = RiskState.COOLDOWN
        self.cooldown_until = time.time() + seconds
    
    def get_status(self) -> Dict:
        """Retorna estado completo del gestor de riesgo"""
        drawdown = 0
        if self.peak_bankroll > 0:
            drawdown = (self.peak_bankroll - self.current_bankroll) / self.peak_bankroll
        
        return {
            'state': self.state.value,
            'bankroll': self.current_bankroll,
            'session_pnl': self.session_pnl,
            'session_pnl_pct': self.session_pnl / self.initial_bankroll if self.initial_bankroll > 0 else 0,
            'peak_bankroll': self.peak_bankroll,
            'drawdown': drawdown,
            'session_time': time.time() - self.session_start_time,
            'consecutive_losses': self.consecutive_losses,
            'consecutive_wins': self.consecutive_wins
        }

