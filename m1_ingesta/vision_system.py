"""Compatibilidad con el sistema de visión mejorado para All Bets Blackjack."""

from __future__ import annotations

from .enhanced_vision_system import AllBetsBlackjackVision, RegionOfInterest

# Mantener el nombre histórico para módulos que aún importan VisionSystem
VisionSystem = AllBetsBlackjackVision

__all__ = ["RegionOfInterest", "AllBetsBlackjackVision", "VisionSystem"]
