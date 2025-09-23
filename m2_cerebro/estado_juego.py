from typing import List, Optional, Dict
from utils.contratos import Card, Hand, GamePhase

class GameState:
    """
    Mantiene el estado actual del juego
    Rastrea manos, fases y estadísticas de la sesión
    """
    
    def __init__(self):
        self.reset_round()
        self.round_count = 0
        self.hands_played = 0
        self.hands_won = 0
        self.hands_lost = 0
        self.hands_pushed = 0
        self.blackjacks = 0
        self.doubles_won = 0
        self.doubles_lost = 0
        
    def reset_round(self):
        """Reinicia el estado para una nueva ronda"""
        self.phase = GamePhase.IDLE
        self.round_id = None
        self.my_hand = Hand(cards=[])
        self.dealer_hand = Hand(cards=[])
        self.shared_cards = []
        self.others_cards = []
        self.last_decision = None
        self.is_doubled = False
        self.is_split = False
        self.insurance_taken = False
        
    def start_round(self, round_id: str):
        """Inicia una nueva ronda"""
        self.reset_round()
        self.round_id = round_id
        self.round_count += 1
        self.phase = GamePhase.BETS_OPEN
        
    def add_shared_card(self, card: Card):
        """Añade una carta a la mano del jugador"""
        self.shared_cards.append(card)
        self.my_hand.add_card(card)
        
        # Verificar blackjack
        if len(self.my_hand.cards) == 2 and self.my_hand.is_blackjack:
            self.blackjacks += 1
        
    def add_dealer_card(self, card: Card, is_hole: bool = False):
        """Añade una carta a la mano del crupier"""
        self.dealer_hand.add_card(card)
        
    def add_others_card(self, card: Card):
        """Añade una carta de otros jugadores"""
        self.others_cards.append(card)
        
    def set_phase(self, phase: GamePhase):
        """Cambia la fase del juego"""
        self.phase = phase
        
    def set_doubled(self, doubled: bool = True):
        """Marca si se dobló la apuesta"""
        self.is_doubled = doubled
        
    def set_split(self, split: bool = True):
        """Marca si se dividió la mano"""
        self.is_split = split
        
    def set_insurance(self, insurance: bool = True):
        """Marca si se tomó seguro"""
        self.insurance_taken = insurance
        
    def record_result(self, result: str):
        """Registra el resultado de una mano"""
        self.hands_played += 1
        
        if result == 'win':
            self.hands_won += 1
            if self.is_doubled:
                self.doubles_won += 1
        elif result == 'loss':
            self.hands_lost += 1
            if self.is_doubled:
                self.doubles_lost += 1
        elif result == 'push':
            self.hands_pushed += 1
    
    def get_state(self) -> Dict:
        """Retorna el estado actual del juego"""
        dealer_up_value = 0
        if self.dealer_hand.cards:
            dealer_up_value = self.dealer_hand.cards[0].value
            
        win_rate = 0
        if self.hands_played > 0:
            win_rate = self.hands_won / self.hands_played
            
        return {
            'round_id': self.round_id,
            'phase': self.phase.value,
            'my_hand_value': self.my_hand.value,
            'my_hand_soft': self.my_hand.is_soft,
            'my_hand_blackjack': self.my_hand.is_blackjack,
            'my_hand_bust': self.my_hand.is_bust,
            'dealer_up_value': dealer_up_value,
            'dealer_hand_value': self.dealer_hand.value,
            'round_count': self.round_count,
            'is_doubled': self.is_doubled,
            'is_split': self.is_split,
            'insurance_taken': self.insurance_taken,
            'stats': {
                'hands_played': self.hands_played,
                'hands_won': self.hands_won,
                'hands_lost': self.hands_lost,
                'hands_pushed': self.hands_pushed,
                'blackjacks': self.blackjacks,
                'doubles_won': self.doubles_won,
                'doubles_lost': self.doubles_lost,
                'win_rate': win_rate
            }
        }
    
    def get_hand_description(self) -> str:
        """Retorna descripción textual de la mano actual"""
        if self.my_hand.is_blackjack:
            return "Blackjack!"
        elif self.my_hand.is_bust:
            return f"Bust ({self.my_hand.value})"
        elif self.my_hand.is_soft:
            return f"Soft {self.my_hand.value}"
        else:
            return f"Hard {self.my_hand.value}"