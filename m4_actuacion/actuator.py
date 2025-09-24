from __future__ import annotations

import importlib
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import pyautogui

from .human_like_mouse import HumanLikeMouse

if importlib.util.find_spec("pytesseract"):
    import pytesseract  # type: ignore
else:  # pragma: no cover - depende de la instalación del entorno
    pytesseract = None  # type: ignore


class GameWindowDetector:
    """Detector específico para la ventana de All Bets Blackjack."""

    def __init__(self) -> None:
        self.cached_window: Optional[object] = None
        self.cache_timestamp: float = 0.0
        self.cache_duration: float = 30.0
        self.window_patterns = [
            {
                "keywords": ["All Bets Blackjack"],
                "priority": 100,
                "min_size": (800, 600),
            },
            {
                "keywords": ["Caliente.mx", "Casino"],
                "priority": 90,
                "min_size": (1000, 700),
            },
            {
                "keywords": ["Caliente.mx", "Blackjack"],
                "priority": 85,
                "min_size": (800, 600),
            },
            {
                "keywords": ["Caliente"],
                "priority": 70,
                "min_size": (800, 600),
            },
        ]

    def get_game_window(self, force_refresh: bool = False) -> Optional[object]:
        """Obtiene la ventana del juego con cache inteligente."""
        current_time = time.time()

        if (
            not force_refresh
            and self.cached_window is not None
            and current_time - self.cache_timestamp < self.cache_duration
        ):
            try:
                if hasattr(self.cached_window, "title") and self.cached_window.title:
                    return self.cached_window
            except Exception:
                pass  # Cache inválido, buscar de nuevo

        game_window = self._find_best_window()
        if game_window is not None:
            self.cached_window = game_window
            self.cache_timestamp = current_time

        return game_window

    def _find_best_window(self) -> Optional[object]:
        try:
            all_windows = pyautogui.getAllWindows()
        except Exception:
            return None

        candidates: List[Dict[str, Union[int, object, str]]] = []
        for window in all_windows:
            if not hasattr(window, "title") or not window.title:
                continue

            score = self._score_window(window)
            if score > 0:
                candidates.append({"window": window, "score": score, "title": window.title})

        if not candidates:
            return None

        candidates.sort(key=lambda item: int(item["score"]), reverse=True)
        best = candidates[0]["window"]
        return best if isinstance(best, object) else None

    def _score_window(self, window: object) -> int:
        if not hasattr(window, "title"):
            return 0

        title_lower = window.title.lower()  # type: ignore[attr-defined]
        best_score = 0

        for pattern in self.window_patterns:
            pattern_score = 0
            for keyword in pattern["keywords"]:
                if keyword.lower() in title_lower:
                    pattern_score += 25

            if pattern_score > 0:
                min_width, min_height = pattern["min_size"]
                width = getattr(window, "width", None)
                height = getattr(window, "height", None)
                if width is not None and height is not None and width >= min_width and height >= min_height:
                    pattern_score += 10
                else:
                    pattern_score = max(0, pattern_score - 20)

            if pattern_score > 0:
                score = pattern["priority"] + pattern_score - 25
                best_score = max(best_score, score)

        return best_score


class HybridActuator:
    """Actuador híbrido que combina coordenadas relativas con template matching."""

    def __init__(self, image_path: str = "m4_actuacion/target_images/") -> None:
        self.mouse = HumanLikeMouse()
        self.image_path = Path(image_path)
        self.window_detector = GameWindowDetector()

        self.action_config: Dict[str, Dict[str, Union[str, Tuple[float, float], Tuple[int, int]]]] = {
            "HIT": {
                "image": "hit_button.png",
                "relative_coords": (0.75, 0.85),
                "expected_size": (80, 40),
                "search_area": (120, 120),
                "description": "Botón PEDIR / HIT",
            },
            "STAND": {
                "image": "stand_button.png",
                "relative_coords": (0.85, 0.85),
                "expected_size": (80, 40),
                "search_area": (120, 120),
                "description": "Botón PLANTARSE / STAND",
            },
            "DOUBLE": {
                "image": "double_button.png",
                "relative_coords": (0.65, 0.85),
                "expected_size": (80, 40),
                "search_area": (120, 120),
                "description": "Botón DOBLAR / DOUBLE",
            },
            "BET_25": {
                "image": "chip_25.png",
                "relative_coords": (0.45, 0.75),
                "expected_size": (50, 50),
                "search_area": (100, 100),
                "description": "Ficha de 25",
            },
            "BET_100": {
                "image": "chip_100.png",
                "relative_coords": (0.55, 0.75),
                "expected_size": (50, 50),
                "search_area": (100, 100),
                "description": "Ficha de 100",
            },
        }

        self.fallback_positions: Dict[str, Tuple[float, float]] = {
            "HIT": (0.75, 0.85),
            "STAND": (0.85, 0.85),
            "DOUBLE": (0.65, 0.85),
            "BET_25": (0.45, 0.75),
            "BET_100": (0.55, 0.75),
        }

        self._last_action_snapshot: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Ejecución principal
    # ------------------------------------------------------------------
    def execute_action(self, action_request: dict) -> dict:
        """Ejecuta una acción con el sistema híbrido."""
        raw_type = action_request.get("type")
        action_type = raw_type.upper() if isinstance(raw_type, str) else ""
        payload = action_request.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        start_time = time.time()

        print(f"🎯 Ejecutando acción: {action_type}")

        if not action_type:
            return self._create_confirmation(
                False,
                (time.time() - start_time) * 1000,
                error="Unknown action type",
            )

        game_window = self.window_detector.get_game_window()
        if not game_window:
            return self._create_confirmation(
                False,
                (time.time() - start_time) * 1000,
                error="Game window not found",
            )

        if action_type == "BET":
            normalized_plan = self._normalize_chip_plan(payload)
            if normalized_plan:
                payload = {**payload, "chip_plan": normalized_plan}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  Intento {attempt + 1}/{max_retries}")
                context_snapshot = self._capture_screen_array()
                if context_snapshot is None:
                    return self._create_confirmation(
                        False,
                        (time.time() - start_time) * 1000,
                        error="Unable to capture screen",
                    )

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

                if action_type == "BET":
                    success = self._execute_bet_action(game_window, payload)
                elif action_type == "PLAY":
                    success = self._execute_play_action(game_window, payload)
                else:
                    success = False

                if success:
                    time.sleep(1)
                    if self._validate_action_effect(action_type, payload, context_snapshot):
                        latency_ms = (time.time() - start_time) * 1000
                        return self._create_confirmation(
                            True,
                            latency_ms,
                            reason=f"Action executed successfully on attempt {attempt + 1}",
                        )

                if attempt < max_retries - 1:
                    time.sleep(1)
                    game_window = self.window_detector.get_game_window(force_refresh=True) or game_window
            except Exception as exc:
                print(f"  ❌ Error en intento {attempt + 1}: {exc}")
                if attempt == max_retries - 1:
                    return self._create_confirmation(
                        False,
                        (time.time() - start_time) * 1000,
                        error=f"Exception after {max_retries} attempts: {exc}",
                    )
                time.sleep(1)

        return self._create_confirmation(
            False,
            (time.time() - start_time) * 1000,
            error="All attempts failed",
        )

    def _execute_play_action(self, game_window: object, payload: Dict[str, Union[str, int]]) -> bool:
        move_raw = payload.get("move") if isinstance(payload, dict) else None
        move = move_raw.upper() if isinstance(move_raw, str) else ""
        if move not in self.action_config:
            print(f"  ❌ Acción desconocida: {move}")
            return False

        target_location = self._find_target_hybrid(game_window, move)
        if not target_location:
            print(f"  ❌ No se encontró objetivo para: {move}")
            return False

        print(f"  ✅ Objetivo encontrado en: {target_location}")
        self.mouse.click(int(target_location[0]), int(target_location[1]))
        return True

    def _execute_bet_action(self, game_window: object, payload: Dict[str, Union[str, int, List[Dict[str, Union[str, int]]]]]) -> bool:
        chip_plan = []
        raw_plan = payload.get("chip_plan") if isinstance(payload, dict) else None
        if isinstance(raw_plan, list) and raw_plan:
            chip_plan = [entry for entry in raw_plan if isinstance(entry, dict)]

        if not chip_plan:
            chip_type = payload.get("chip_type") if isinstance(payload, dict) else None
            if not isinstance(chip_type, str):
                chip_type = payload.get("chip") if isinstance(payload, dict) else None
            if not isinstance(chip_type, str):
                chip_type = "BET_25"
            clicks = payload.get("clicks", 1) if isinstance(payload, dict) else 1
            try:
                click_count = int(clicks)
            except (TypeError, ValueError):
                click_count = 1
            chip_plan = [{"chip_type": chip_type, "count": max(1, click_count)}]

        for entry in chip_plan:
            chip_type = entry.get("chip_type") if isinstance(entry, dict) else None
            if not isinstance(chip_type, str):
                print("  ⚠️ Tipo de ficha inválido en plan de apuestas")
                continue

            try:
                count = int(entry.get("count", 1)) if isinstance(entry, dict) else 1
            except (TypeError, ValueError):
                count = 1
            if count <= 0:
                continue

            target_location = self._find_target_hybrid(game_window, chip_type)
            if not target_location:
                print(f"  ❌ No se encontró ficha: {chip_type}")
                return False

            print(f"  💰 Haciendo {count} clics en {chip_type} en {target_location}")
            for _ in range(count):
                self.mouse.click(int(target_location[0]), int(target_location[1]))
                time.sleep(0.1)

        return True

    # ------------------------------------------------------------------
    # Métodos de búsqueda
    # ------------------------------------------------------------------
    def _find_target_hybrid(self, game_window: object, action_key: str) -> Optional[Tuple[int, int]]:
        config = self.action_config.get(action_key)
        if not config:
            return self._find_by_fallback_position(game_window, action_key)

        coords_result = self._find_by_relative_coordinates(game_window, config)
        if coords_result:
            print("    📍 Encontrado por coordenadas relativas")
            return coords_result

        template_result = self._find_by_template_matching_focused(game_window, config)
        if template_result:
            print("    🔍 Encontrado por template matching dirigido")
            return template_result

        image_name = config.get("image")
        if isinstance(image_name, str):
            full_result = self._find_by_full_template_matching(image_name)
            if full_result:
                print("    🌐 Encontrado por template matching completo")
                return (int(full_result[0]), int(full_result[1]))

        fallback_result = self._find_by_fallback_position(game_window, action_key)
        if fallback_result:
            print("    🎯 Usando posición de fallback")
            return fallback_result

        return None

    def _find_by_relative_coordinates(
        self, game_window: object, config: Dict[str, Union[str, Tuple[float, float], Tuple[int, int]]]
    ) -> Optional[Tuple[int, int]]:
        relative_coords = config.get("relative_coords")
        if not isinstance(relative_coords, tuple) or len(relative_coords) != 2:
            return None

        try:
            window_width = getattr(game_window, "width", None)
            window_height = getattr(game_window, "height", None)
            window_left = getattr(game_window, "left", 0)
            window_top = getattr(game_window, "top", 0)

            if window_width is None or window_height is None:
                screen_size = pyautogui.size()
                window_width = screen_size.width
                window_height = screen_size.height

            rel_x, rel_y = relative_coords
            abs_x = int(window_left + window_width * rel_x)
            abs_y = int(window_top + window_height * rel_y)

            if self._verify_coordinates_validity(abs_x, abs_y, config):
                return (abs_x, abs_y)
        except Exception as exc:
            print(f"    ⚠️ Error en coordenadas relativas: {exc}")

        return None

    def _verify_coordinates_validity(
        self, x: int, y: int, config: Dict[str, Union[str, Tuple[float, float], Tuple[int, int]]]
    ) -> bool:
        try:
            region_size = 60
            screen_size = pyautogui.size()
            half = region_size // 2
            left = max(0, x - half)
            top = max(0, y - half)
            width = min(region_size, max(0, screen_size.width - left))
            height = min(region_size, max(0, screen_size.height - top))
            if width == 0 or height == 0:
                return False

            screenshot = pyautogui.screenshot(region=(left, top, width, height))
            region_array = np.array(screenshot)
            if region_array.ndim == 3 and region_array.shape[2] == 4:
                region_array = cv2.cvtColor(region_array, cv2.COLOR_RGBA2RGB)
            elif region_array.ndim == 2:
                region_array = cv2.cvtColor(region_array, cv2.COLOR_GRAY2RGB)

            if region_array.size == 0:
                return False

            std_dev = float(np.std(region_array))
            if std_dev < 5:
                return False

            expected_size = config.get("expected_size")
            if isinstance(expected_size, tuple) and expected_size and expected_size[0] > 70:
                return self._has_button_like_colors(region_array)
            return self._has_chip_like_colors(region_array)
        except Exception:
            return True

    def _has_button_like_colors(self, region_array: np.ndarray) -> bool:
        hsv_region = cv2.cvtColor(region_array, cv2.COLOR_RGB2HSV)
        color_ranges = [
            ((40, 50, 50), (80, 255, 255)),
            ((0, 50, 50), (20, 255, 255)),
            ((160, 50, 50), (180, 255, 255)),
            ((20, 50, 50), (40, 255, 255)),
            ((100, 50, 50), (140, 255, 255)),
        ]

        total_pixels = region_array.shape[0] * region_array.shape[1]
        color_pixels = 0
        for lower, upper in color_ranges:
            mask = cv2.inRange(hsv_region, np.array(lower), np.array(upper))
            color_pixels += int(np.count_nonzero(mask))

        return total_pixels > 0 and (color_pixels / total_pixels) > 0.15

    def _has_chip_like_colors(self, region_array: np.ndarray) -> bool:
        hsv_region = cv2.cvtColor(region_array, cv2.COLOR_RGB2HSV)
        gray_region = cv2.cvtColor(region_array, cv2.COLOR_RGB2GRAY)
        circles = cv2.HoughCircles(
            gray_region,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=20,
            param1=50,
            param2=30,
            minRadius=10,
            maxRadius=30,
        )

        if circles is not None and len(circles) > 0:
            return True

        std_dev = float(np.std(hsv_region))
        return std_dev > 15

    def _find_by_template_matching_focused(
        self, game_window: object, config: Dict[str, Union[str, Tuple[float, float], Tuple[int, int]]]
    ) -> Optional[Tuple[int, int]]:
        relative_coords = config.get("relative_coords")
        search_area = config.get("search_area")
        image_file = config.get("image")
        if (
            not isinstance(relative_coords, tuple)
            or not isinstance(search_area, tuple)
            or not isinstance(image_file, str)
        ):
            return None

        try:
            window_width = getattr(game_window, "width", None)
            window_height = getattr(game_window, "height", None)
            window_left = getattr(game_window, "left", 0)
            window_top = getattr(game_window, "top", 0)

            if window_width is None or window_height is None:
                screen_size = pyautogui.size()
                window_width = screen_size.width
                window_height = screen_size.height

            rel_x, rel_y = relative_coords
            center_x = int(window_left + window_width * rel_x)
            center_y = int(window_top + window_height * rel_y)

            search_w, search_h = search_area
            half_w = search_w // 2
            half_h = search_h // 2

            screen_size = pyautogui.size()
            search_left = max(0, center_x - half_w)
            search_top = max(0, center_y - half_h)
            search_right = min(screen_size.width, center_x + half_w)
            search_bottom = min(screen_size.height, center_y + half_h)
            region_width = max(0, search_right - search_left)
            region_height = max(0, search_bottom - search_top)

            if region_width == 0 or region_height == 0:
                return None

            screenshot = pyautogui.screenshot(
                region=(search_left, search_top, region_width, region_height)
            )
            screenshot_np = np.array(screenshot)
            if screenshot_np.ndim == 3 and screenshot_np.shape[2] == 4:
                screenshot_np = cv2.cvtColor(screenshot_np, cv2.COLOR_RGBA2RGB)
            elif screenshot_np.ndim == 2:
                screenshot_np = cv2.cvtColor(screenshot_np, cv2.COLOR_GRAY2RGB)
            search_region = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

            template_path = self.image_path / image_file
            if not template_path.exists():
                return None

            template = cv2.imread(str(template_path))
            if template is None:
                return None

            result = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > 0.75:
                template_h, template_w = template.shape[:2]
                global_x = search_left + max_loc[0] + template_w // 2
                global_y = search_top + max_loc[1] + template_h // 2
                return (global_x, global_y)
        except Exception as exc:
            print(f"    ⚠️ Error en template matching dirigido: {exc}")

        return None

    def _find_by_full_template_matching(self, image_file: str) -> Optional[Tuple[int, int]]:
        try:
            template_path = self.image_path / image_file
            if not template_path.exists():
                return None

            location = pyautogui.locateCenterOnScreen(str(template_path), confidence=0.8)
            if location:
                return (int(location[0]), int(location[1]))

            location = pyautogui.locateCenterOnScreen(str(template_path), confidence=0.7)
            if location:
                return (int(location[0]), int(location[1]))
        except pyautogui.ImageNotFoundException:
            return None
        except Exception as exc:
            print(f"    ⚠️ Error en template matching completo: {exc}")

        return None

    def _find_by_fallback_position(self, game_window: object, action_key: str) -> Optional[Tuple[int, int]]:
        fallback_coords = self.fallback_positions.get(action_key)
        if not fallback_coords:
            return None

        try:
            window_width = getattr(game_window, "width", None)
            window_height = getattr(game_window, "height", None)
            window_left = getattr(game_window, "left", 0)
            window_top = getattr(game_window, "top", 0)

            if window_width is None or window_height is None:
                screen_size = pyautogui.size()
                window_width = screen_size.width
                window_height = screen_size.height

            rel_x, rel_y = fallback_coords
            abs_x = int(window_left + window_width * rel_x)
            abs_y = int(window_top + window_height * rel_y)
            return (abs_x, abs_y)
        except Exception as exc:
            print(f"    ⚠️ Error en posición de fallback: {exc}")
            return None

    # ------------------------------------------------------------------
    # Validaciones de contexto y efectos
    # ------------------------------------------------------------------
    def _validate_action_context(
        self, action_type: Optional[str], screenshot: Optional[np.ndarray] = None
    ) -> bool:
        if not action_type:
            return False

        if screenshot is None:
            screenshot = self._capture_screen_array()
            if screenshot is None:
                return False

        if action_type == "PLAY":
            return not self._says_place_bets(screenshot)

        if action_type == "BET":
            return self._says_place_bets(screenshot) or self._in_betting_phase(screenshot)

        return True

    def _validate_action_effect(
        self,
        action_type: Optional[str],
        payload: Dict[str, Union[str, int, List[Dict[str, Union[str, int]]]]],
        before_snapshot: Optional[np.ndarray] = None,
    ) -> bool:
        time.sleep(1)
        after_snapshot = self._capture_screen_array()
        if after_snapshot is None:
            return False

        if action_type == "PLAY":
            move_raw = payload.get("move") if isinstance(payload, dict) else None
            move = move_raw.upper() if isinstance(move_raw, str) else ""
            if move == "HIT":
                return self._cards_increased(before_snapshot, after_snapshot)
            if move == "STAND":
                return not self._has_action_buttons()
            if move == "DOUBLE":
                return self._cards_increased(before_snapshot, after_snapshot)

        if action_type == "BET":
            return self._chip_on_table(before_snapshot, after_snapshot) or self._betting_area_changed(
                before_snapshot, after_snapshot
            )

        return True

    # ------------------------------------------------------------------
    # Utilidades de análisis visual
    # ------------------------------------------------------------------
    def _capture_screen_array(self) -> Optional[np.ndarray]:
        try:
            screenshot = pyautogui.screenshot()
        except Exception:
            return None

        screenshot_np = np.array(screenshot)
        if screenshot_np.ndim == 3 and screenshot_np.shape[2] == 4:
            screenshot_np = cv2.cvtColor(screenshot_np, cv2.COLOR_RGBA2RGB)
        elif screenshot_np.ndim == 2:
            screenshot_np = cv2.cvtColor(screenshot_np, cv2.COLOR_GRAY2RGB)
        return screenshot_np

    def _says_place_bets(self, screenshot: np.ndarray) -> bool:
        if pytesseract is None:
            return False

        try:
            h, w = screenshot.shape[:2]
            text_region = screenshot[h // 3 : 2 * h // 3, w // 4 : 3 * w // 4]
            text = pytesseract.image_to_string(text_region).lower()
        except Exception:
            return False

        keywords = (
            "place your bets",
            "place bets",
            "haz tu apuesta",
            "apuesta",
            "bets open",
            "betting time",
        )
        return any(keyword in text for keyword in keywords)

    def _in_betting_phase(self, screenshot: np.ndarray) -> bool:
        try:
            hsv_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGB2HSV)
            h, w = hsv_screenshot.shape[:2]
            betting_area = hsv_screenshot[2 * h // 3 : h, w // 4 : 3 * w // 4]

            chip_colors = [
                ((0, 100, 100), (10, 255, 255)),
                ((170, 100, 100), (180, 255, 255)),
                ((40, 100, 100), (80, 255, 255)),
                ((100, 100, 100), (140, 255, 255)),
                ((0, 0, 0), (180, 50, 50)),
            ]

            total_pixels = betting_area.shape[0] * betting_area.shape[1]
            chip_pixels = 0
            for lower, upper in chip_colors:
                mask = cv2.inRange(betting_area, np.array(lower), np.array(upper))
                chip_pixels += int(np.count_nonzero(mask))

            return total_pixels > 0 and (chip_pixels / total_pixels) > 0.02
        except Exception:
            return False

    def _has_action_buttons(self) -> bool:
        for action_key in ("HIT", "STAND", "DOUBLE"):
            config = self.action_config.get(action_key)
            image_name = config.get("image") if isinstance(config, dict) else None
            if not isinstance(image_name, str):
                continue
            template_path = self.image_path / image_name
            if not template_path.exists():
                continue
            try:
                location = pyautogui.locateCenterOnScreen(str(template_path), confidence=0.7)
            except pyautogui.ImageNotFoundException:
                location = None
            except Exception:
                location = None
            if location:
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

    def _betting_area_changed(
        self, before_snapshot: Optional[np.ndarray], after_snapshot: np.ndarray
    ) -> bool:
        if before_snapshot is None:
            return True

        h_after, w_after = after_snapshot.shape[:2]
        h_before, w_before = before_snapshot.shape[:2]
        h = min(h_after, h_before)
        w = min(w_after, w_before)
        if h == 0 or w == 0:
            return False

        betting_region_before = before_snapshot[2 * h // 3 : h, w // 4 : 3 * w // 4]
        betting_region_after = after_snapshot[2 * h // 3 : h, w // 4 : 3 * w // 4]

        if betting_region_before.shape != betting_region_after.shape:
            return True

        diff = np.mean(
            np.abs(
                betting_region_after.astype(np.int16) - betting_region_before.astype(np.int16)
            )
        )
        return diff > 10

    def _frame_difference(self, before: np.ndarray, after: np.ndarray) -> float:
        min_h = min(before.shape[0], after.shape[0])
        min_w = min(before.shape[1], after.shape[1])
        if min_h == 0 or min_w == 0:
            return 0.0
        before_crop = before[:min_h, :min_w]
        after_crop = after[:min_h, :min_w]
        delta = np.abs(after_crop.astype(np.int16) - before_crop.astype(np.int16))
        return float(delta.mean() / 255.0)

    def _create_confirmation(self, ok: bool, latency: float, reason: str = "", error: Optional[str] = None) -> dict:
        confirmation = {
            "t": time.time(),
            "event": "ACTION_CONFIRMED",
            "ok": ok,
            "latency_ms": latency,
            "reason": reason,
            "trace_id": f"trace-{random.randint(1000, 9999)}",
        }
        if error:
            confirmation["error"] = error
        return confirmation

    def trigger_recalibration(self) -> None:
        print("[HybridActuator] Triggering recalibration - clearing window cache")
        self.window_detector.cached_window = None
        self.window_detector.cache_timestamp = 0.0

    def get_status(self) -> dict:
        game_window = self.window_detector.get_game_window()
        cache_age = time.time() - self.window_detector.cache_timestamp if self.window_detector.cache_timestamp else 0.0
        status = {
            "window_detected": game_window is not None,
            "window_title": getattr(game_window, "title", "") if game_window else "",
            "cached_window": self.window_detector.cached_window is not None,
            "cache_age": cache_age,
            "available_actions": list(self.action_config.keys()),
        }
        if game_window:
            status.update(
                {
                    "window_size": f"{getattr(game_window, 'width', 0)}x{getattr(game_window, 'height', 0)}",
                    "window_position": f"({getattr(game_window, 'left', 0)}, {getattr(game_window, 'top', 0)})",
                }
            )
        return status

    def _normalize_chip_plan(
        self, payload: Dict[str, Union[str, int, List[Dict[str, Union[str, int]]]]]
    ) -> List[Dict[str, int]]:
        plan: List[Dict[str, int]] = []

        raw_plan = payload.get("chip_plan") if isinstance(payload, dict) else None
        if isinstance(raw_plan, list):
            for entry in raw_plan:
                if not isinstance(entry, dict):
                    continue
                chip_type = entry.get("chip_type")
                if not isinstance(chip_type, str):
                    continue
                try:
                    count = int(entry.get("count", 1))
                except (TypeError, ValueError):
                    count = 1
                if count <= 0:
                    continue
                plan.append({"chip_type": chip_type, "count": count})

        if not plan and isinstance(payload, dict):
            chip_type = payload.get("chip_type") or payload.get("chip")
            if isinstance(chip_type, str):
                try:
                    clicks = int(payload.get("clicks", 1))
                except (TypeError, ValueError):
                    clicks = 1
                plan.append({"chip_type": chip_type, "count": max(1, clicks)})

        return plan


class SafetyWrapper:
    """Wrapper de seguridad para el actuador híbrido."""

    def __init__(self, actuator: HybridActuator) -> None:
        self.actuator = actuator
        self.consecutive_failures = 0
        self.max_failures = 3
        self.last_success_time = time.time()
        self.action_history: List[Dict[str, Union[float, str, dict]]] = []

    def safe_execute(self, action_request: dict) -> dict:
        try:
            timestamp = time.time()
            self.action_history.append(
                {
                    "timestamp": timestamp,
                    "action": action_request.get("type"),
                    "payload": action_request.get("payload", {}),
                }
            )
            if len(self.action_history) > 10:
                self.action_history.pop(0)

            result = self.actuator.execute_action(action_request)
            if result.get("ok"):
                self.consecutive_failures = 0
                self.last_success_time = timestamp
            else:
                self.consecutive_failures += 1
                if self.consecutive_failures >= self.max_failures:
                    return {
                        "ok": False,
                        "error": "Safety limit reached - stopping bot",
                        "consecutive_failures": self.consecutive_failures,
                        "last_success": timestamp - self.last_success_time,
                    }

            return result
        except Exception as exc:
            self.consecutive_failures += 1
            return {
                "ok": False,
                "error": f"Safety wrapper caught: {exc}",
                "consecutive_failures": self.consecutive_failures,
            }

    def get_safety_status(self) -> dict:
        return {
            "consecutive_failures": self.consecutive_failures,
            "max_failures": self.max_failures,
            "last_success_age": time.time() - self.last_success_time,
            "recent_actions": len(self.action_history),
            "actuator_status": self.actuator.get_status(),
        }


class Actuator(HybridActuator):
    """Alias de compatibilidad para el actuador híbrido."""

    pass
