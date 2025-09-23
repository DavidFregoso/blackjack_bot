from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import time

class EventType(Enum):
    # Eventos de M1
    ROUND_START = "ROUND_START"
    ROUND_END = "ROUND_END"
    CARD_DEALT_SHARED = "CARD_DEALT_SHARED"
    CARD_DEALT = "CARD_DEALT"
    STATE_TEXT = "STATE_TEXT"
    MY_DECISION_LOCKED = "MY_DECISION_LOCKED"
    
    # Eventos de M2
    TC_SNAPSHOT = "TC_SNAPSHOT"
    RC_UPDATE = "RC_UPDATE"
    STATE_UPDATE = "STATE_UPDATE"
    
    # Eventos de M3
    PLAY_ADVICE = "PLAY_ADVICE"
    BET_ADVICE_NEXT_ROUND = "BET_ADVICE_NEXT_ROUND"
    RISK_ALERT = "RISK_ALERT"
    
    # Eventos de M4
    ACTION_REQUEST = "ACTION_REQUEST"
    ACTION_CONFIRMED = "ACTION_CONFIRMED"

class GamePhase(Enum):
    IDLE = "idle"
    BETS_OPEN = "bets_open"
    DEALING = "dealing"
    MY_ACTION = "my_action"
    OTHERS_ACTIONS = "others_actions"
    DEALER_PLAY = "dealer_play"
    PAYOUTS = "payouts"

class PlayAction(Enum):
    HIT = "HIT"
    STAND = "STAND"
    DOUBLE = "DOUBLE"
    SPLIT = "SPLIT"
    SURRENDER = "SURRENDER"
    INSURANCE = "INSURANCE"

@dataclass
class Event:
    timestamp: float
    event_type: EventType
    round_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def create(cls, event_type: EventType, round_id: Optional[str] = None, **kwargs):
        return cls(
            timestamp=time.time(),
            event_type=event_type,
            round_id=round_id,
            data=kwargs
        )

@dataclass
class Card:
    rank: str  # '2'-'9', 'T', 'J', 'Q', 'K', 'A'
    suit: str  # 'H', 'D', 'C', 'S'
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    @property
    def value(self) -> int:
        if self.rank in 'JQK':
            return 10
        elif self.rank == 'A':
            return 11  # Soft ace
        elif self.rank == 'T':
            return 10
        else:
            return int(self.rank)
    
    @property
    def count_value_hilo(self) -> int:
        if self.rank in '23456':
            return 1
        elif self.rank in '789':
            return 0
        elif self.rank in 'TJQKA':
            return -1
        return 0
    
    @property
    def count_value_zen(self) -> int:
        if self.rank in '23':
            return 1
        elif self.rank in '456':
            return 2
        elif self.rank == '7':
            return 1
        elif self.rank in '89':
            return 0
        elif self.rank in 'TJQK':
            return -2
        elif self.rank == 'A':
            return -1
        return 0

@dataclass
class Hand:
    cards: List[Card]
    
    def add_card(self, card: Card):
        self.cards.append(card)
    
    @property
    def value(self) -> int:
        total = sum(card.value for card in self.cards)
        aces = sum(1 for card in self.cards if card.rank == 'A')
        
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        
        return total
    
    @property
    def is_soft(self) -> bool:
        total = sum(card.value for card in self.cards)
        aces = sum(1 for card in self.cards if card.rank == 'A')
        
        if aces == 0:
            return False
        
        return total <= 21
    
    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.value == 21
    
    @property
    def is_bust(self) -> bool:
        return self.value > 21
    
    def __str__(self):
        return ' '.join(str(card) for card in self.cards)
