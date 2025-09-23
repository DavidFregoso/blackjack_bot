import json
import time
from typing import List, Dict, Generator
from utils.contratos import Event, EventType, Card

class M1Simulator:
    
    def __init__(self):
        self.round_files = [
            'simulador/rondas_prueba/ronda_bj.json',
            'simulador/rondas_prueba/ronda_crupier_se_pasa.json',
            'simulador/rondas_prueba/ronda_conteo_alto.json'
        ]
        self.current_round_idx = 0
    
    def load_round(self, filepath: str) -> List[Event]:
        try:
            with open(filepath, 'r') as f:
                round_data = json.load(f)
            
            events = []
            for event_data in round_data['events']:
                event = Event(
                    timestamp=event_data['timestamp'],
                    event_type=EventType[event_data['event_type']],
                    round_id=event_data.get('round_id'),
                    data=event_data.get('data', {})
                )
                events.append(event)
            
            return events
        except Exception as e:
            print(f"Error loading round file {filepath}: {e}")
            return []
    
    def generate_events(self) -> Generator[Event, None, None]:
        for round_file in self.round_files:
            events = self.load_round(round_file)
            for event in events:
                yield event
                time.sleep(0.1)  # Simular latencia
    
    def parse_card(self, card_str: str) -> Card:
        if len(card_str) != 2:
            raise ValueError(f"Invalid card string: {card_str}")
        
        rank = card_str[0]
        suit = card_str[1]
        return Card(rank=rank, suit=suit)