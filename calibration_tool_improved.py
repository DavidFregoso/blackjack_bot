"""Wrapper para exponer la calibración mejorada sin intervención manual."""

from __future__ import annotations

from calibration_tool import CalibrationTool


class ImprovedCalibrationTool(CalibrationTool):
    """Extiende la herramienta clásica con un punto de entrada semántico."""

    def run_enhanced_calibration(self) -> bool:
        """Ejecuta la calibración híbrida optimizada para All Bets Blackjack."""

        return self.run_calibration()


__all__ = ["ImprovedCalibrationTool"]
