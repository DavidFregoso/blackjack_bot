"""Módulo 1 - Ingesta (Visión por Computadora).

Este paquete contiene los componentes responsables de observar la mesa
de Blackjack, reconocer cartas y estados del juego y emitir eventos
estandarizados que el resto del sistema puede consumir.
"""

from .card_recognizer import CardRecognizer
from .vision_system import RegionOfInterest, VisionSystem

__all__ = [
    "CardRecognizer",
    "RegionOfInterest",
    "VisionSystem",
]
