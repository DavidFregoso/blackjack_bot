"""Compatibilidad con el sistema de actuadores híbridos mejorado.

Este módulo actúa como punto de entrada para el sistema híbrido
combinando coordenadas relativas y template matching. Se expone para
mantener compatibilidad con integraciones que esperan importar desde
``m4_actuacion.hybrid_actuator_system``.
"""

from __future__ import annotations

from .actuator import GameWindowDetector, HybridActuator, SafetyWrapper

__all__ = [
    "HybridActuator",
    "SafetyWrapper",
    "GameWindowDetector",
]
