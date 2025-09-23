import json
from typing import Dict, Optional
from pathlib import Path

from utils.contratos import Card

class CardCounter:
    """
    Implementa el conteo de cartas usando Hi-Lo y Zen
    Mantiene snapshots de TC para el formato de mano compartida
    """
    
    def __init__(self, config_path: str = "configs/settings.json", system: Optional[str] = None):
        # Cargar configuración
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            # Configuración por defecto
            self.config = {
                'rules': {'decks': 8},
                'counting': {'system': 'hilo'}
            }
        
        self.decks = self.config['rules']['decks']
        self.total_cards = self.decks * 52
        config_system = self.config.get('counting', {}).get('system', 'hilo')
        self.system = system or config_system
        
        self.reset()
    
    def reset(self):
        """Reinicia todos los contadores"""
        self.running_count_hilo = 0
        self.running_count_zen = 0
        self.cards_seen = 0
        
        # Snapshots para mano compartida
        self.tc_pre = 0.0   # Para decisiones de jugada
        self.tc_mid = 0.0   # Después de otros jugadores
        self.tc_post = 0.0  # Después del dealer, para próxima apuesta
        
        # Historial de cartas
        self.cards_history = []
    
    def process_card(self, card: Card):
        """Procesa una carta y actualiza el conteo para ambos sistemas."""
        if not isinstance(card, Card):
            return

        # Actualizar conteo Hi-Lo
        self.running_count_hilo += card.count_value_hilo

        # Actualizar conteo Zen
        self.running_count_zen += card.count_value_zen

        # Incrementar cartas vistas
        self.cards_seen += 1

        # Agregar al historial
        self.cards_history.append(str(card))

        # Limitar historial a últimas 100 cartas
        if len(self.cards_history) > 100:
            self.cards_history.pop(0)
    
    @property
    def decks_remaining(self) -> float:
        """Calcula los mazos restantes"""
        cards_remaining = self.total_cards - self.cards_seen
        return max(0.25, cards_remaining / 52)  # Mínimo 0.25 mazos
    
    @property
    def penetration(self) -> float:
        """Calcula la penetración del zapato"""
        if self.total_cards == 0:
            return 0.0
        return self.cards_seen / self.total_cards
    
    @property
    def true_count_hilo(self) -> float:
        """Calcula el True Count para Hi-Lo"""
        if self.decks_remaining <= 0:
            return 0.0
        return self.running_count_hilo / self.decks_remaining
    
    @property
    def true_count_zen(self) -> float:
        """Calcula el True Count para Zen"""
        if self.decks_remaining <= 0:
            return 0.0
        return self.running_count_zen / self.decks_remaining

    @property
    def true_count(self) -> float:
        """Calcula el True Count según el sistema seleccionado."""
        if self.decks_remaining <= 0:
            return 0.0

        if self.system == 'zen':
            return self.running_count_zen / self.decks_remaining
        return self.running_count_hilo / self.decks_remaining
    
    def snapshot_pre(self) -> float:
        """
        Captura TC_pre: antes de decisiones del jugador
        Usado para decisiones de jugada (hit/stand/double)
        """
        self.tc_pre = self.true_count
        return self.tc_pre
    
    def snapshot_mid(self) -> float:
        """
        Captura TC_mid: después de que otros jugadores actúan
        Perfila la próxima apuesta mientras otros juegan
        """
        self.tc_mid = self.true_count
        return self.tc_mid
    
    def snapshot_post(self) -> float:
        """
        Captura TC_post: después del crupier
        Base para la apuesta de la siguiente ronda
        """
        self.tc_post = self.true_count
        return self.tc_post
    
    def get_snapshot(self) -> Dict:
        """Retorna el estado completo del conteo"""
        return {
            'rc_hilo': self.running_count_hilo,
            'rc_zen': self.running_count_zen,
            'tc_pre': self.tc_pre,
            'tc_mid': self.tc_mid,
            'tc_post': self.tc_post,
            'tc_current': self.true_count,
            'tc_current_hilo': self.true_count_hilo,
            'tc_current_zen': self.true_count_zen,
            'decks_remaining': self.decks_remaining,
            'cards_seen': self.cards_seen,
            'penetration': self.penetration,
            'counting_system': self.system
        }

    def get_advantage(self) -> float:
        """
        Calcula la ventaja del jugador basada en TC
        Fórmula aproximada: ventaja = (TC - 0.5) * 0.5%
        """
        tc = self.true_count
        advantage = (tc - 0.5) * 0.005
        return max(-0.02, advantage)  # Límite inferior -2%
