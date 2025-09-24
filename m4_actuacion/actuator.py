from __future__ import annotations

import importlib
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyautogui

from .human_like_mouse import HumanLikeMouse


if importlib.util.find_spec("pytesseract"):
    import pytesseract
    from pytesseract import Output
else:  # pragma: no cover - depende de la instalación del entorno
    pytesseract = None  # type: ignore
    Output = None  # type: ignore


class Actuator:
    """Recibe órdenes del M3 y las ejecuta buscando imágenes en pantalla."""
    def __init__(self, image_path: str = "m4_actuacion/target_images/"):
        self.mouse = HumanLikeMouse()
        self.image_path = Path(image_path)
        self.action_map = {
            "HIT": "hit_button.png",
            "STAND": "stand_button.png",
            "DOUBLE": "double_button.png",
            "BET_25": "chip_25.png",
            "BET_100": "chip_100.png",
        }
        self.approx_positions: Dict[str, Tuple[float, float]] = {
            "HIT": (0.8, 0.75),
            "STAND": (0.9, 0.75),
            "DOUBLE": (0.7, 0.75),
            "BET_25": (0.5, 0.85),
            "BET_100": (0.55, 0.85),
        }
        self._last_action_snapshot: Optional[np.ndarray] = None

    def _find_image_on_screen(self, image_name: str, confidence=0.85) -> tuple | None:
        """Busca una imagen en la pantalla y devuelve las coordenadas de su centro."""
        try:
            image_file = self.image_path / image_name
            location = pyautogui.locateCenterOnScreen(str(image_file), confidence=confidence)
            return location
        except pyautogui.ImageNotFoundException:
            return None # Es normal no encontrar una imagen si no es el momento de la acción
        except Exception as e:
            print(f"⚠️ [M4 Actuator] Error inesperado buscando imagen: {e}")
            return None

    def execute_action(self, action_request: dict):
        """Ejecuta una acción con múltiples capas de verificación."""
        action_type = action_request.get("type")
        payload = action_request.get("payload", {})
        start_time = time.time()

        chip_plan: List[Dict[str, int | str]] = []
        if action_type == "BET":
            chip_plan = self._normalize_chip_plan(payload)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                context_snapshot = self._capture_screen_array()
                if not self._validate_action_context(action_type, context_snapshot):
                    if attempt == max_retries - 1:
                        return self._create_confirmation(
                            False,
                            (time.time() - start_time) * 1000,
                            error="Action context validation failed",
                        )
                    time.sleep(1)
                    continue

                self._last_action_snapshot = context_snapshot

                if action_type == "BET" and chip_plan:
                    executed = self._execute_bet_plan(chip_plan)
                    if not executed:
                        if attempt == max_retries - 1:
                            return self._create_confirmation(
                                False,
                                (time.time() - start_time) * 1000,
                                error="Bet plan could not be executed",
                            )
                        time.sleep(1)
                        continue
                else:
                    target_location = self._find_target_robust(action_type, payload)
                    if not target_location:
                        if attempt == max_retries - 1:
                            return self._create_confirmation(
                                False,
                                (time.time() - start_time) * 1000,
                                error=f"Target not found after {max_retries} attempts",
                            )
                        time.sleep(1)
                        continue

                    self.mouse.click(int(target_location[0]), int(target_location[1]))

                if self._validate_action_effect(action_type, payload, context_snapshot):
                    latency_ms = (time.time() - start_time) * 1000
                    return self._create_confirmation(
                        True,
                        latency_ms,
                        reason=f"Action executed successfully on attempt {attempt + 1}",
                    )

                if attempt < max_retries - 1:
                    time.sleep(1)
            except Exception as exc:
                if attempt == max_retries - 1:
                    latency_ms = (time.time() - start_time) * 1000
                    return self._create_confirmation(
                        False,
                        latency_ms,
                        error=f"Exception after {max_retries} attempts: {exc}",
                    )
                time.sleep(1)

        return self._create_confirmation(
            False,
            (time.time() - start_time) * 1000,
            error="Unknown failure",
        )

    def trigger_recalibration(self) -> None:
        """Hook para solicitar recalibración en caso de errores repetidos."""
        print("[Actuator] Recalibration requested due to persistent failures")

    # ------------------------------------------------------------------
    # Métodos auxiliares de búsqueda
    # ------------------------------------------------------------------
    def _find_target_robust(self, action_type: Optional[str], payload: Dict) -> Optional[Tuple[int, int]]:
        if action_type == "PLAY":
            move = payload.get("move")
            image_name = self.action_map.get(move)
            if not image_name:
                return None

            location = self._find_image_on_screen(image_name, confidence=0.85)
            if location:
                return location

            location = self._find_image_on_screen(image_name, confidence=0.7)
            if location:
                return location

            return self._find_by_approximate_position(move)

        if action_type == "BET":
            chip_type = payload.get("chip_type") or payload.get("chip")
            if not chip_type and payload.get("chip_plan"):
                first = payload["chip_plan"][0]
                if isinstance(first, dict):
                    chip_type = first.get("chip_type")

            key = chip_type or "BET_25"
            image_name = self.action_map.get(key)
            if image_name:
                location = self._find_image_on_screen(image_name, confidence=0.85)
                if location:
                    return location

                location = self._find_image_on_screen(image_name, confidence=0.7)
                if location:
                    return location

            return self._find_by_approximate_position(key)

        return None

    def _normalize_chip_plan(self, payload: Dict) -> List[Dict[str, int | str]]:
        plan: List[Dict[str, int | str]] = []

        raw_plan = payload.get("chip_plan")
        if isinstance(raw_plan, list):
            for entry in raw_plan:
                if not isinstance(entry, dict):
                    continue
                chip_type = entry.get("chip_type")
                if not chip_type:
                    continue
                try:
                    count = int(entry.get("count", 1))
                except (TypeError, ValueError):
                    count = 1
                if count <= 0:
                    continue
                plan.append({"chip_type": chip_type, "count": count})

        if not plan:
            chip_type = payload.get("chip_type") or payload.get("chip")
            if chip_type:
                try:
                    clicks = int(payload.get("clicks", 1))
                except (TypeError, ValueError):
                    clicks = 1
                plan.append({"chip_type": chip_type, "count": max(1, clicks)})

        return plan

    def _execute_bet_plan(self, plan: List[Dict[str, int | str]]) -> bool:
        for entry in plan:
            chip_type = entry.get("chip_type")
            if not chip_type:
                continue

            try:
                count = int(entry.get("count", 1))
            except (TypeError, ValueError):
                count = 1

            if count <= 0:
                continue

            location = self._find_target_robust("BET", {"chip_type": chip_type})
            if not location:
                print(f"⚠️ [M4 Actuator] No se encontró la ficha {chip_type}")
                return False

            for _ in range(count):
                self.mouse.click(int(location[0]), int(location[1]))

        return True

    def _find_by_approximate_position(self, identifier: Optional[str]) -> Optional[Tuple[int, int]]:
        if not identifier:
            return None

        normalized = self.approx_positions.get(identifier)
        if not normalized:
            return None

        screen_size = pyautogui.size()
        x = int(screen_size.width * normalized[0])
        y = int(screen_size.height * normalized[1])
        return (x, y)

    # ------------------------------------------------------------------
    # Validaciones de contexto y efectos
    # ------------------------------------------------------------------
    def _validate_action_context(
        self, action_type: Optional[str], screenshot: Optional[np.ndarray] = None
    ) -> bool:
        if action_type is None:
            return False

        if screenshot is None:
            screenshot = self._capture_screen_array()

        if action_type == "PLAY":
            return not self._says_place_bets(screenshot)

        if action_type == "BET":
            return self._says_place_bets(screenshot)

        return True

    def _validate_action_effect(
        self,
        action_type: Optional[str],
        payload: Dict,
        before_snapshot: Optional[np.ndarray] = None,
    ) -> bool:
        time.sleep(1)
        after_snapshot = self._capture_screen_array()

        if action_type == "PLAY":
            move = payload.get("move")
            if move == "HIT":
                return self._cards_increased(before_snapshot, after_snapshot)
            if move == "STAND":
                return not self._has_action_buttons()
            if move == "DOUBLE":
                return self._cards_increased(before_snapshot, after_snapshot)

        if action_type == "BET":
            return self._chip_on_table(before_snapshot, after_snapshot)

        return True

    # ------------------------------------------------------------------
    # Utilidades de análisis visual
    # ------------------------------------------------------------------
    def _capture_screen_array(self) -> np.ndarray:
        screenshot = pyautogui.screenshot()
        return np.array(screenshot)

    def _says_place_bets(self, screenshot: np.ndarray) -> bool:
        if pytesseract is None or Output is None:
            return False

        try:
            text = pytesseract.image_to_string(screenshot).lower()
        except Exception:
            return False

        keywords = ("place your bets", "place bets", "apuesta", "bets open")
        return any(keyword in text for keyword in keywords)

    def _has_action_buttons(self) -> bool:
        for move_key in ("HIT", "STAND", "DOUBLE"):
            image_name = self.action_map.get(move_key)
            if not image_name:
                continue
            if self._find_image_on_screen(image_name, confidence=0.7):
                return True
        return False

    def _cards_increased(
        self, before_snapshot: Optional[np.ndarray], after_snapshot: np.ndarray
    ) -> bool:
        if before_snapshot is None:
            return True

        diff = self._frame_difference(before_snapshot, after_snapshot)
        return diff > 0.02

    def _chip_on_table(
        self, before_snapshot: Optional[np.ndarray], after_snapshot: np.ndarray
    ) -> bool:
        if before_snapshot is None:
            return True
        diff = self._frame_difference(before_snapshot, after_snapshot)
        return diff > 0.015

    def _frame_difference(self, before: np.ndarray, after: np.ndarray) -> float:
        if before.shape != after.shape:
            before = before[: after.shape[0], : after.shape[1]]
        delta = np.abs(after.astype(np.int16) - before.astype(np.int16))
        return float(delta.mean() / 255.0)

    def _create_confirmation(self, ok: bool, latency: float, reason: str = "", error=None):
        """Crea el evento ACTION_CONFIRMED estandarizado."""
        confirmation = {
            "t": time.time(), "event": "ACTION_CONFIRMED", "ok": ok,
            "latency_ms": latency, "reason": reason,
            "trace_id": f"trace-{random.randint(1000, 9999)}"
        }
        if error:
            confirmation["error"] = error
        return confirmation


class SafetyWrapper:
    def __init__(self, actuator: Actuator):
        self.actuator = actuator
        self.consecutive_failures = 0
        self.max_failures = 3

    def safe_execute(self, action_request: dict):
        try:
            result = self.actuator.execute_action(action_request)
            if result.get("ok"):
                self.consecutive_failures = 0
            else:
                self.consecutive_failures += 1

            if self.consecutive_failures >= self.max_failures:
                return {"ok": False, "error": "Safety limit reached - stopping bot"}

            return result

        except Exception as exc:
            self.consecutive_failures += 1
            return {"ok": False, "error": f"Safety wrapper caught: {exc}"}
