import json
import math
from typing import Tuple
from pathlib import Path

class BetPolicy:
    """
    Sistema de apuestas basado en True Count
    Implementa rampa de apuesta y Kelly Criterion
    """
    
    def __init__(self, config_path: str = "configs/decision.json"):
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = self.get_default_config()
        
        self.base_unit = self.config['limits']['unit_value']
        self.table_min = self.config['limits']['table_min']
        self.table_max = self.config['limits']['table_max']
        
        self.bet_policy = self.config.get('bet_policy', {})
        self.policy_type = self.bet_policy.get('type', 'ramp')
        
        # Rampa de apuesta por TC
        self.bet_ramp = {
            -2: 0,    # No jugar
            -1: 1,    # 1 unidad
            0: 1,     # 1 unidad
            1: 2,     # 2 unidades
            2: 4,     # 4 unidades
            3: 6,     # 6 unidades
            4: 8,     # 8 unidades
            5: 10     # 10 unidades
        }
        
        # Actualizar con config si existe
        if 'ramp' in self.bet_policy:
            for tc_str, units in self.bet_policy['ramp'].items():
                self.bet_ramp[int(tc_str)] = units
    
    def get_default_config(self):
        """Configuración por defecto si no existe archivo"""
        return {
            'limits': {
                'table_min': 25,
                'table_max': 1000,
                'unit_value': 25
            },
            'bet_policy': {
                'type': 'ramp'
            },
            'cadence': {
                'skip_negative_tc': -1
            }
        }
    
    def calculate_bet(self, tc: float, bankroll: float, 
                     risk_factor: float = 1.0) -> Tuple[float, str]:
        """
        Calcula la apuesta óptima basada en TC y bankroll
        
        Args:
            tc: True Count actual
            bankroll: Bankroll disponible
            risk_factor: Factor de reducción por riesgo (0-1)
        
        Returns:
            Tuple de (monto_apuesta, explicación)
        """
        
        # TC para apuesta usa decimal
        tc_bet = tc
        
        if self.policy_type == 'ramp':
            units = self.get_ramp_units(tc_bet)
        elif self.policy_type == 'kelly':
            units = self.get_kelly_units(tc_bet, bankroll)
        else:
            units = 1
        
        # Aplicar factor de riesgo
        units = units * risk_factor
        
        # Calcular monto
        bet_amount = units * self.base_unit
        
        # Aplicar límites de mesa
        bet_amount = max(self.table_min, min(bet_amount, self.table_max))
        
        # No apostar más del 5% del bankroll
        max_bet = bankroll * 0.05
        bet_amount = min(bet_amount, max_bet)
        
        # Redondear a múltiplo de 5
        bet_amount = round(bet_amount / 5) * 5
        
        rationale = f"TC={tc_bet:.2f}, Units={units:.1f}, Policy={self.policy_type}"
        
        return bet_amount, rationale
    
    def get_ramp_units(self, tc: float) -> float:
        """Obtiene unidades según rampa de apuesta"""
        # Interpolar entre valores de la rampa
        tc_floor = math.floor(tc)
        tc_ceil = math.ceil(tc)
        
        if tc_floor == tc_ceil:
            return self.bet_ramp.get(tc_floor, 1)
        
        units_floor = self.bet_ramp.get(tc_floor, 1)
        units_ceil = self.bet_ramp.get(tc_ceil, 1)
        
        # Interpolación lineal
        fraction = tc - tc_floor
        units = units_floor + (units_ceil - units_floor) * fraction
        
        return max(0, units)
    
    def get_kelly_units(self, tc: float, bankroll: float) -> float:
        """Calcula unidades usando Kelly Criterion"""
        # Kelly simplificado para Blackjack
        # Ventaja aproximada = (TC - 0.5) * 0.5%
        advantage = (tc - 0.5) * 0.005
        
        if advantage <= 0:
            return 1
        
        # Kelly fraction (simplificado)
        kelly_fraction = advantage / 1.1  # Divisor conservador
        
        # Aplicar Kelly fraccionario (25% de Kelly completo)
        kelly_fraction *= 0.25
        
        # Convertir a unidades
        bet_size = bankroll * kelly_fraction
        units = bet_size / self.base_unit
        
        return max(1, min(units, 10))
    
    def should_sit_out(self, tc: float) -> bool:
        """Determina si sentarse basado en TC"""
        skip_tc = self.config.get('cadence', {}).get('skip_negative_tc', -1)
        return tc < skip_tc