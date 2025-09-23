import json
import math
from typing import Tuple, Optional
from utils.contratos import PlayAction

class PlayPolicy:
    def __init__(self):
        self.load_basic_strategy()
        self.load_indices()
    
    def load_basic_strategy(self):
        # Estrategia básica para H17, DAS, No Surrender, 8 mazos
        self.hard_table = {
            # Dealer:  2    3    4    5    6    7    8    9    T    A
            5:  ['H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H'],
            6:  ['H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H'],
            7:  ['H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H'],
            8:  ['H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H', 'H'],
            9:  ['H', 'D', 'D', 'D', 'D', 'H', 'H', 'H', 'H', 'H'],
            10: ['D', 'D', 'D', 'D', 'D', 'D', 'D', 'D', 'H', 'H'],
            11: ['D', 'D', 'D', 'D', 'D', 'D', 'D', 'D', 'D', 'H'],
            12: ['H', 'H', 'S', 'S', 'S', 'H', 'H', 'H', 'H', 'H'],
            13: ['S', 'S', 'S', 'S', 'S', 'H', 'H', 'H', 'H', 'H'],
            14: ['S', 'S', 'S', 'S', 'S', 'H', 'H', 'H', 'H', 'H'],
            15: ['S', 'S', 'S', 'S', 'S', 'H', 'H', 'H', 'H', 'H'],
            16: ['S', 'S', 'S', 'S', 'S', 'H', 'H', 'H', 'H', 'H'],
            17: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            18: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            19: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            20: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            21: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S']
        }
        
        self.soft_table = {
            # Dealer:  2    3    4    5    6    7    8    9    T    A
            13: ['H', 'H', 'H', 'D', 'D', 'H', 'H', 'H', 'H', 'H'],
            14: ['H', 'H', 'H', 'D', 'D', 'H', 'H', 'H', 'H', 'H'],
            15: ['H', 'H', 'D', 'D', 'D', 'H', 'H', 'H', 'H', 'H'],
            16: ['H', 'H', 'D', 'D', 'D', 'H', 'H', 'H', 'H', 'H'],
            17: ['H', 'D', 'D', 'D', 'D', 'H', 'H', 'H', 'H', 'H'],
            18: ['S', 'D', 'D', 'D', 'D', 'S', 'S', 'H', 'H', 'H'],
            19: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            20: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            21: ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S']
        }
        
        self.pair_table = {
            # Dealer:  2    3    4    5    6    7    8    9    T    A
            'A': ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
            'T': ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S', 'S'],
            '9': ['P', 'P', 'P', 'P', 'P', 'S', 'P', 'P', 'S', 'S'],
            '8': ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
            '7': ['P', 'P', 'P', 'P', 'P', 'P', 'H', 'H', 'H', 'H'],
            '6': ['P', 'P', 'P', 'P', 'P', 'H', 'H', 'H', 'H', 'H'],
            '5': ['D', 'D', 'D', 'D', 'D', 'D', 'D', 'D', 'H', 'H'],
            '4': ['H', 'H', 'H', 'P', 'P', 'H', 'H', 'H', 'H', 'H'],
            '3': ['P', 'P', 'P', 'P', 'P', 'P', 'H', 'H', 'H', 'H'],
            '2': ['P', 'P', 'P', 'P', 'P', 'P', 'H', 'H', 'H', 'H']
        }
    
    def load_indices(self):
        try:
            with open('configs/indices.json', 'r') as f:
                self.indices = json.load(f)
        except:
            self.indices = {}
    
    def get_decision(self, hand_value: int, is_soft: bool, dealer_up: int, 
                    tc: float, can_double: bool = True, can_split: bool = False) -> Tuple[PlayAction, str]:
        
        # Floor TC para índices
        tc_floor = math.floor(tc)
        
        # Verificar desviaciones por índice
        deviation = self.check_deviation(hand_value, is_soft, dealer_up, tc_floor)
        if deviation:
            return deviation
        
        # Estrategia básica
        dealer_idx = self._dealer_to_index(dealer_up)
        
        if is_soft:
            if hand_value < 13:
                hand_value = 13
            if hand_value > 21:
                hand_value = 21
            action_code = self.soft_table.get(hand_value, ['S'] * 10)[dealer_idx]
        else:
            if hand_value < 5:
                hand_value = 5
            if hand_value > 21:
                hand_value = 21
            action_code = self.hard_table.get(hand_value, ['S'] * 10)[dealer_idx]
        
        # Convertir código a acción
        if action_code == 'H':
            return PlayAction.HIT, "Basic Strategy"
        elif action_code == 'S':
            return PlayAction.STAND, "Basic Strategy"
        elif action_code == 'D':
            if can_double:
                return PlayAction.DOUBLE, "Basic Strategy"
            else:
                return PlayAction.HIT, "Basic Strategy (D→H)"
        elif action_code == 'P':
            if can_split:
                return PlayAction.SPLIT, "Basic Strategy"
            else:
                return PlayAction.HIT, "Basic Strategy (P→H)"
        
        return PlayAction.STAND, "Default"
    
    def check_deviation(self, hand_value: int, is_soft: bool, dealer_up: int, 
                        tc: int) -> Optional[Tuple[PlayAction, str]]:
        
        # Desviaciones más importantes por TC
        if tc >= 3:
            if hand_value == 12 and dealer_up == 2:
                return PlayAction.STAND, f"Index Play (TC={tc})"
            if hand_value == 12 and dealer_up == 3:
                return PlayAction.STAND, f"Index Play (TC={tc})"
        
        if tc >= 4:
            if hand_value == 10 and dealer_up == 10:
                return PlayAction.DOUBLE, f"Index Play (TC={tc})"
            if hand_value == 10 and dealer_up == 11:
                return PlayAction.DOUBLE, f"Index Play (TC={tc})"
        
        if tc <= -1:
            if hand_value == 13 and dealer_up == 2:
                return PlayAction.HIT, f"Index Play (TC={tc})"
            if hand_value == 13 and dealer_up == 3:
                return PlayAction.HIT, f"Index Play (TC={tc})"
        
        return None
    
    def _dealer_to_index(self, dealer_up: int) -> int:
        if dealer_up == 11:  # Ace
            return 9
        elif dealer_up == 10:  # 10, J, Q, K
            return 8
        else:
            return dealer_up - 2  # 2-9