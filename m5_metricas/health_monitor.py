"""Herramientas para monitorear la salud general del bot en tiempo real."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HealthMetrics:
    actions_success_rate: float = 1.0
    ocr_confidence_avg: float = 0.8
    phase_transition_errors: int = 0
    bankroll_read_failures: int = 0
    last_health_check: float = field(default_factory=time.time)


class HealthMonitor:
    """Monitoriza métricas clave del bot para detectar comportamientos anómalos."""

    def __init__(self) -> None:
        self.metrics = HealthMetrics()
        self._recent_actions: List[bool] = []
        self._recent_confidences: List[float] = []

    # ------------------------------------------------------------------
    # Actualizaciones de métricas
    # ------------------------------------------------------------------
    def update_action_result(self, success: bool) -> None:
        """Registra el resultado de una acción ejecutada por el actuador."""
        self._recent_actions.append(success)
        if len(self._recent_actions) > 10:
            self._recent_actions.pop(0)

        self.metrics.actions_success_rate = sum(self._recent_actions) / len(self._recent_actions)
        self.metrics.last_health_check = time.time()

    def update_ocr_confidence(self, confidence: float) -> None:
        self._recent_confidences.append(confidence)
        if len(self._recent_confidences) > 10:
            self._recent_confidences.pop(0)

        if self._recent_confidences:
            self.metrics.ocr_confidence_avg = sum(self._recent_confidences) / len(self._recent_confidences)
        self.metrics.last_health_check = time.time()

    def increment_phase_error(self) -> None:
        self.metrics.phase_transition_errors += 1
        self.metrics.last_health_check = time.time()

    def increment_bankroll_failure(self) -> None:
        self.metrics.bankroll_read_failures += 1
        self.metrics.last_health_check = time.time()

    # ------------------------------------------------------------------
    # Reportes
    # ------------------------------------------------------------------
    def get_health_status(self) -> str:
        issues = []
        if self.metrics.actions_success_rate < 0.7:
            issues.append("Low action success rate")
        if self.metrics.ocr_confidence_avg < 0.6:
            issues.append("Poor OCR performance")
        if self.metrics.phase_transition_errors > 5:
            issues.append("FSM instability")
        if self.metrics.bankroll_read_failures > 3:
            issues.append("Bankroll reader unstable")

        if not issues:
            return "HEALTHY"
        if len(issues) <= 2:
            return "WARNING"
        return "CRITICAL"

    def generate_health_report(self) -> Dict[str, object]:
        return {
            "status": self.get_health_status(),
            "metrics": {
                "actions_success_rate": self.metrics.actions_success_rate,
                "ocr_confidence_avg": self.metrics.ocr_confidence_avg,
                "phase_transition_errors": self.metrics.phase_transition_errors,
                "bankroll_read_failures": self.metrics.bankroll_read_failures,
            },
            "timestamp": time.time(),
        }
