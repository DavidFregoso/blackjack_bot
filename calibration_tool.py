"""Herramienta interactiva mejorada para capturar y calibrar imágenes objetivo del módulo M4.

Esta utilidad incorpora un sistema híbrido de calibración que combina detección
automática optimizada para la mesa *All Bets Blackjack* con un flujo manual de
respaldo cuando es necesario. El objetivo es reducir la intervención humana,
agilizar la configuración inicial y mantener compatibilidad con el flujo clásico
de calibración.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pyautogui


@dataclass
class TargetDescriptor:
    """Información asociada a cada elemento a calibrar."""

    name: str
    description: str
    filename: Optional[str] = None
    expected_size: Optional[Tuple[int, int]] = None
    relative_coords: Optional[Tuple[float, float]] = None


class CalibrationTool:
    """Herramienta interactiva para capturar y calibrar imágenes objetivo."""

    def __init__(
        self,
        output_dir: str = "m4_actuacion/target_images/",
        settings_path: str = "configs/settings.json",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.settings_path = Path(settings_path)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

        self._roi_data: Dict[str, Dict[str, int]] = {}
        self._roi_settings: Dict[str, Dict[str, int]] = self._load_existing_rois()

        # Algunos sistemas lanzan excepciones si el cursor alcanza la esquina
        # superior izquierda. Deshabilitamos el "failsafe" para evitar abortos
        # inesperados durante la calibración interactiva.
        pyautogui.FAILSAFE = False

        self.drawing = False
        self.start_point: Optional[Tuple[int, int]] = None
        self.current_screenshot: Optional[np.ndarray] = None
        self.current_selection: Optional[Tuple[int, int, int, int]] = None

        # Caché simple para reutilizar la ventana detectada previamente
        self._cached_window_signature: Optional[Tuple[str, int, int, int, int]] = None

        self.calibration_config: Dict[str, Dict[str, TargetDescriptor]] = {
            "buttons": {
                "hit_button": TargetDescriptor(
                    name="Botón PEDIR / HIT",
                    filename="hit_button.png",
                    description="Botón verde '+' para pedir carta",
                    expected_size=(80, 40),
                    relative_coords=(0.75, 0.85),
                ),
                "stand_button": TargetDescriptor(
                    name="Botón PLANTARSE / STAND",
                    filename="stand_button.png",
                    description="Botón rojo 'Ø' para plantarse",
                    expected_size=(80, 40),
                    relative_coords=(0.85, 0.85),
                ),
                "double_button": TargetDescriptor(
                    name="Botón DOBLAR / DOUBLE",
                    filename="double_button.png",
                    description="Botón amarillo 'x2' para doblar",
                    expected_size=(80, 40),
                    relative_coords=(0.65, 0.85),
                ),
                "chip_25": TargetDescriptor(
                    name="Ficha de 25",
                    filename="chip_25.png",
                    description="Ficha de valor 25 (habitualmente color rojo o verde)",
                    expected_size=(50, 50),
                    relative_coords=(0.45, 0.75),
                ),
                "chip_100": TargetDescriptor(
                    name="Ficha de 100",
                    filename="chip_100.png",
                    description="Ficha de valor 100 (habitualmente color negro)",
                    expected_size=(50, 50),
                    relative_coords=(0.55, 0.75),
                ),
            },
            "rois": {
                "bankroll_area": TargetDescriptor(
                    name="Área del bankroll",
                    description="Región donde aparece el saldo actual del jugador",
                    expected_size=(150, 30),
                    relative_coords=(0.85, 0.05),
                ),
                "dealer_cards": TargetDescriptor(
                    name="Cartas del crupier",
                    description="Región donde aparecen las cartas del crupier",
                    expected_size=(200, 120),
                    relative_coords=(0.50, 0.20),
                ),
                "player_cards": TargetDescriptor(
                    name="Cartas del jugador",
                    description="Región donde aparecen las cartas del jugador principal",
                    expected_size=(250, 150),
                    relative_coords=(0.50, 0.65),
                ),
                "game_status": TargetDescriptor(
                    name="Estado del juego",
                    description="Zona donde aparecen los mensajes principales del juego",
                    expected_size=(400, 80),
                    relative_coords=(0.50, 0.45),
                ),
                "others_cards_area": TargetDescriptor(
                    name="Área de cartas de otros jugadores",
                    description="Región ampliada para divisiones y manos adicionales",
                    expected_size=(1200, 200),
                    relative_coords=(0.50, 0.40),
                ),
            },
        }

        # Patrones de búsqueda ordenados por prioridad para encontrar la ventana correcta
        self.window_search_patterns: List[Dict[str, object]] = [
            {
                "title_keywords": ["All Bets Blackjack"],
                "priority": 100,
                "description": "Título específico del juego",
            },
            {
                "title_keywords": ["Caliente.mx", "Casino"],
                "min_size": (1000, 700),
                "priority": 90,
                "description": "Ventana de Caliente con casino",
            },
            {
                "title_keywords": ["Caliente.mx", "Blackjack"],
                "priority": 85,
                "description": "Caliente con blackjack en título",
            },
            {
                "title_keywords": ["Caliente"],
                "min_size": (800, 600),
                "priority": 70,
                "description": "Ventana principal de Caliente",
            },
            {
                "title_keywords": ["Chrome", "Caliente"],
                "priority": 60,
                "description": "Chrome con Caliente en título",
            },
            {
                "title_keywords": ["Chrome"],
                "min_size": (1200, 800),
                "url_indicators": ["caliente"],
                "priority": 50,
                "description": "Chrome grande (probablemente el juego)",
            },
        ]

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------
    def run_calibration(self) -> bool:
        """Ejecuta el proceso completo de calibración con flujo híbrido."""
        self._print_banner()

        print("\n🔍 Detectando ventana de 'All Bets Blackjack'…")
        game_window = self._find_game_window_enhanced()

        if not game_window:
            print("\n⚠️  No se pudo detectar automáticamente la ventana del juego.")
            print("Asegúrate de que:")
            print("  1. Caliente.mx esté abierto con la mesa de All Bets Blackjack")
            print("  2. La mesa esté visible y activa")
            print("  3. La ventana no esté minimizada ni cubierta por otras aplicaciones")

            if not self._prompt_yes_no("¿Quieres continuar con calibración manual? [s/N]: ", default=False):
                return False
            return self._run_manual_calibration()

        print("\n🎯 Configurando sistema híbrido…")
        if not self._setup_preconfigured_coordinates(game_window):
            print("❌ Error configurando coordenadas automáticas. Se recurrirá al modo manual.")
            return self._run_manual_calibration()

        print("\n🔍 Verificando detección de botones…")
        verification_passed = 0
        total_buttons = len(self.calibration_config["buttons"])
        for button_id, descriptor in self.calibration_config["buttons"].items():
            if self._verify_with_template_matching(button_id, descriptor):
                verification_passed += 1

        print(f"\n📊 Verificación automática: {verification_passed}/{total_buttons} botones detectables")

        if verification_passed >= max(1, int(total_buttons * 0.6)):
            print("✅ Sistema híbrido configurado correctamente.")
            self._update_settings_config()
            print(f"📁 Plantillas guardadas en: {self.output_dir.resolve()}")
            print(f"🛠  Configuración actualizada en: {self.settings_path.resolve()}")
            return True

        print("⚠️  Baja tasa de detección automática. Se continuará con calibración manual completa.")
        return self._run_manual_calibration()

    # ------------------------------------------------------------------
    # Sistema de detección mejorado
    # ------------------------------------------------------------------
    def _window_signature(self, window) -> Tuple[str, int, int, int, int]:
        title = getattr(window, "title", "") or ""
        return (
            title.strip(),
            int(getattr(window, "left", 0)),
            int(getattr(window, "top", 0)),
            int(getattr(window, "width", 0)),
            int(getattr(window, "height", 0)),
        )

    def _find_game_window_enhanced(self) -> Optional[object]:
        """Sistema mejorado de detección de ventana específica."""
        print("🔍 Buscando ventana de 'All Bets Blackjack'…")

        try:
            all_windows = pyautogui.getAllWindows()
        except Exception as exc:
            print(f"❌ Error obteniendo ventanas: {exc}")
            return None

        if not all_windows:
            print("❌ No se encontraron ventanas abiertas para analizar.")
            return None

        # Intento rápido usando la caché almacenada
        if self._cached_window_signature:
            cached_title, _cached_left, _cached_top, cached_width, cached_height = (
                self._cached_window_signature
            )
            for window in all_windows:
                title = getattr(window, "title", "") or ""
                if not title.strip():
                    continue
                signature = self._window_signature(window)
                if (
                    signature[0].lower() == cached_title.lower()
                    and abs(signature[3] - cached_width) <= 30
                    and abs(signature[4] - cached_height) <= 30
                ):
                    try:
                        window.activate()
                        time.sleep(1.0)
                    except Exception as exc:
                        print(f"⚠️  Error reactivando ventana en caché: {exc}")
                    else:
                        print(f"🧠 Ventana en caché reutilizada: {signature[0]}")
                    self._cached_window_signature = signature
                    return window

        candidates: List[Dict[str, object]] = []
        for window in all_windows:
            title = getattr(window, "title", "") or ""
            title = title.strip()
            if len(title) < 3:
                continue

            score = self._score_window(window, title)
            if score <= 0:
                continue

            signature = self._window_signature(window)
            candidates.append(
                {
                    "window": window,
                    "title": signature[0],
                    "score": score,
                    "width": signature[3],
                    "height": signature[4],
                    "signature": signature,
                }
            )

        if not candidates:
            print("❌ No se encontraron ventanas candidatas que coincidan con los patrones.")
            return None

        candidates.sort(key=lambda item: int(item["score"]), reverse=True)

        print("📋 Ventanas candidatas encontradas:")
        for index, candidate in enumerate(candidates[:5]):
            print(
                f"  {index + 1}. {candidate['title']} "
                f"(Score: {candidate['score']}, Size: {candidate['width']}x{candidate['height']})"
            )

        if len(candidates) > 1 and int(candidates[1]["score"]) >= 70:
            selected = self._user_select_window(candidates)
            if selected is not None:
                return selected
            return None

        best_candidate = candidates[0]
        try:
            best_candidate["window"].activate()
            time.sleep(1.5)
        except Exception as exc:
            print(f"⚠️  Error activando ventana: {exc}")

        self._cached_window_signature = best_candidate["signature"]
        print(f"✅ Ventana seleccionada automáticamente: {best_candidate['title']}")
        return best_candidate["window"]

    def _score_window(self, window, title: str) -> int:
        """Calcula puntuación de ventana basada en patrones específicos."""
        title_lower = title.lower()
        score = 0

        for pattern in self.window_search_patterns:
            pattern_score = 0

            keywords = pattern.get("title_keywords", [])
            for keyword in keywords:
                if keyword and str(keyword).lower() in title_lower:
                    pattern_score += 20

            min_size = pattern.get("min_size")
            if min_size and hasattr(window, "width") and hasattr(window, "height"):
                if window.width >= min_size[0] and window.height >= min_size[1]:
                    pattern_score += 10
                else:
                    pattern_score = max(0, pattern_score - 15)

            if pattern_score > 0:
                priority = int(pattern.get("priority", 0))
                score = max(score, priority + pattern_score - 20)

        return score

    def _user_select_window(self, candidates: List[Dict[str, object]]) -> Optional[object]:
        """Permite al usuario seleccionar entre múltiples ventanas candidatas."""
        print("\n🤔 Se encontraron múltiples ventanas candidatas: ")
        print("Selecciona la ventana correcta del juego:")

        limited = candidates[:5]
        for index, candidate in enumerate(limited):
            print(f"  {index + 1}. {candidate['title']}")
            print(
                f"     Tamaño: {candidate['width']}x{candidate['height']} | "
                f"Puntuación: {candidate['score']}"
            )
            print()

        while True:
            choice = input("Ingresa el número (1-5) o 'c' para cancelar: ").strip().lower()
            if choice == "c":
                return None

            try:
                index = int(choice) - 1
            except ValueError:
                print("❌ Por favor ingresa un número válido.")
                continue

            if 0 <= index < len(limited):
                selected = limited[index]
                try:
                    selected["window"].activate()
                    time.sleep(1.5)
                except Exception as exc:
                    print(f"⚠️  Error activando la ventana seleccionada: {exc}")

                self._cached_window_signature = selected["signature"]
                print(f"✅ Seleccionada: {selected['title']}")
                return selected["window"]

            print("❌ Número fuera de rango, intenta nuevamente.")

    # ------------------------------------------------------------------
    # Sistema híbrido - Coordenadas automáticas
    # ------------------------------------------------------------------
    def _setup_preconfigured_coordinates(self, game_window) -> bool:
        """Configura coordenadas preconfiguradas basadas en la ventana del juego."""
        if not game_window:
            return False

        print("🎯 Configurando coordenadas preconfiguradas…")

        window_width = int(getattr(game_window, "width", 1200))
        window_height = int(getattr(game_window, "height", 800))
        window_left = int(getattr(game_window, "left", 0))
        window_top = int(getattr(game_window, "top", 0))

        self._roi_data.clear()

        for roi_id, descriptor in self.calibration_config["rois"].items():
            if not descriptor.relative_coords:
                continue

            rel_x, rel_y = descriptor.relative_coords
            exp_width, exp_height = descriptor.expected_size or (100, 50)

            center_x = int(window_left + window_width * rel_x)
            center_y = int(window_top + window_height * rel_y)

            left = center_x - exp_width // 2
            top = center_y - exp_height // 2

            roi_data = {
                "left": left,
                "top": top,
                "width": exp_width,
                "height": exp_height,
            }

            self._roi_data[roi_id] = roi_data
            self._roi_settings[roi_id] = roi_data
            print(
                f"✅ ROI {descriptor.name}: x={left}, y={top}, w={exp_width}, h={exp_height}"
            )

        try:
            screenshot = self._capture_screenshot()
        except Exception as exc:
            print(f"❌ No se pudo capturar la pantalla para extraer botones: {exc}")
            return False

        auto_success = True
        for button_id, descriptor in self.calibration_config["buttons"].items():
            if not descriptor.relative_coords or not descriptor.filename:
                continue

            if self._extract_button_from_coordinates(
                screenshot, game_window, button_id, descriptor
            ):
                print(f"✅ Botón {descriptor.name} extraído automáticamente")
            else:
                print(f"⚠️  No se pudo extraer automáticamente {descriptor.name}")
                auto_success = False

        return auto_success

    def _extract_button_from_coordinates(
        self,
        screenshot: np.ndarray,
        game_window,
        _button_id: str,
        descriptor: TargetDescriptor,
    ) -> bool:
        """Extrae imagen de botón usando coordenadas relativas."""
        if not descriptor.relative_coords or not descriptor.filename:
            return False

        window_width = int(getattr(game_window, "width", screenshot.shape[1]))
        window_height = int(getattr(game_window, "height", screenshot.shape[0]))
        window_left = int(getattr(game_window, "left", 0))
        window_top = int(getattr(game_window, "top", 0))

        rel_x, rel_y = descriptor.relative_coords
        exp_width, exp_height = descriptor.expected_size or (80, 40)

        center_x = int(window_left + window_width * rel_x)
        center_y = int(window_top + window_height * rel_y)

        margin = 20
        extract_left = max(0, center_x - exp_width // 2 - margin)
        extract_top = max(0, center_y - exp_height // 2 - margin)
        extract_right = min(screenshot.shape[1], center_x + exp_width // 2 + margin)
        extract_bottom = min(screenshot.shape[0], center_y + exp_height // 2 + margin)

        extracted_region = screenshot[extract_top:extract_bottom, extract_left:extract_right]

        if extracted_region.size == 0:
            return False

        valid, message = self._validate_button_image(
            extracted_region, descriptor.expected_size
        )
        if not valid:
            print(f"⚠️  Región extraída no válida para {descriptor.name}: {message}")
            return False

        output_path = self.output_dir / descriptor.filename
        try:
            cv2.imwrite(str(output_path), extracted_region)
        except Exception as exc:
            print(f"❌ Error guardando {output_path}: {exc}")
            return False

        return True

    def _verify_with_template_matching(
        self, _button_id: str, descriptor: TargetDescriptor
    ) -> bool:
        """Verifica que el botón extraído se pueda encontrar en pantalla."""
        if not descriptor.filename:
            return True

        template_path = self.output_dir / descriptor.filename
        if not template_path.exists():
            return False

        try:
            screenshot = self._capture_screenshot()
            template = cv2.imread(str(template_path))
            if template is None:
                print(f"⚠️  No se pudo leer la plantilla {template_path} para verificación.")
                return False

            gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            scales = [0.8, 0.9, 1.0, 1.1, 1.2]
            best_confidence = 0.0
            for scale in scales:
                if scale != 1.0:
                    width = int(gray_template.shape[1] * scale)
                    height = int(gray_template.shape[0] * scale)
                    if width <= 0 or height <= 0:
                        continue
                    scaled_template = cv2.resize(gray_template, (width, height))
                else:
                    scaled_template = gray_template

                result = cv2.matchTemplate(
                    gray_screenshot, scaled_template, cv2.TM_CCOEFF_NORMED
                )
                _, max_val, _, _ = cv2.minMaxLoc(result)
                best_confidence = max(best_confidence, float(max_val))

            print(f"   Verificación {descriptor.name}: confianza {best_confidence:.2f}")
            return best_confidence > 0.7
        except Exception as exc:
            print(f"⚠️  Error en verificación de {descriptor.name}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Entrada manual (respaldo)
    # ------------------------------------------------------------------
    def _run_manual_calibration(self) -> bool:
        """Ejecuta la calibración manual completa como respaldo."""
        print("\n📸 Iniciando calibración manual…")

        print("\n🔘 Calibrando botones de acción…")
        for target_id, descriptor in self.calibration_config["buttons"].items():
            if not self._calibrate_target(target_id, descriptor, target_type="button"):
                print(f"⚠️  Se omitió la calibración de {descriptor.name}.")

        print("\n🔍 Calibrando regiones de interés…")
        for target_id, descriptor in self.calibration_config["rois"].items():
            if not self._calibrate_target(target_id, descriptor, target_type="roi"):
                print(f"⚠️  Se omitió la calibración de {descriptor.name}.")

        self._update_settings_config()
        print("\n✅ Calibración manual completada.")
        print(f"📁 Plantillas guardadas en: {self.output_dir.resolve()}")
        print(f"🛠  Configuración actualizada en: {self.settings_path.resolve()}")
        return True

    # ------------------------------------------------------------------
    # Calibración individual
    # ------------------------------------------------------------------
    def _calibrate_target(
        self,
        target_id: str,
        descriptor: TargetDescriptor,
        target_type: str,
    ) -> bool:
        print("\n" + "-" * 60)
        print(f"📍 Calibrando: {descriptor.name}")
        print(f"    {descriptor.description}")

        if target_type == "button" and descriptor.filename:
            existing_path = self.output_dir / descriptor.filename
            if existing_path.exists():
                if self._handle_existing_button(existing_path, descriptor):
                    return True
        elif target_type == "roi":
            if target_id in self._roi_settings:
                if self._handle_existing_roi(target_id, descriptor):
                    return True

        try:
            screenshot = self._capture_screenshot()
        except Exception as exc:  # pragma: no cover - interacción manual
            print(f"❌ No fue posible obtener la captura de pantalla: {exc}")
            return False

        if target_type == "button":
            return self._calibrate_button(target_id, descriptor, screenshot)
        return self._calibrate_roi(target_id, descriptor, screenshot)

    # ------------------------------------------------------------------
    # Gestión de botones
    # ------------------------------------------------------------------
    def _calibrate_button(
        self,
        target_id: str,
        descriptor: TargetDescriptor,
        screenshot: np.ndarray,
    ) -> bool:
        assert descriptor.filename, "Los botones deben definir un nombre de archivo"
        window_name = f"Calibrar: {descriptor.name}"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.imshow(window_name, screenshot)
        print("    • Posiciona el cursor sobre el botón y presiona ESPACIO para capturar.")
        print("    • Presiona R para refrescar la captura actual.")
        print("    • Presiona ESC para omitir este elemento.")

        try:
            while True:
                key = cv2.waitKey(50) & 0xFF
                if key == 27:  # ESC
                    print("⏭️  Elemento omitido por el usuario.")
                    return False
                if key == ord("r"):
                    screenshot = self._capture_screenshot(refresh_notice=True)
                    cv2.imshow(window_name, screenshot)
                if key == 32:  # SPACE
                    cursor_x, cursor_y = pyautogui.position()
                    sub_image = self._extract_button_region(
                        screenshot, (cursor_x, cursor_y), descriptor
                    )
                    valid, message = self._validate_button_image(
                        sub_image, descriptor.expected_size
                    )
                    if not valid:
                        print(f"❌ Captura inválida: {message}")
                        continue

                    output_path = self.output_dir / descriptor.filename
                    try:
                        cv2.imwrite(str(output_path), sub_image)
                    except Exception as exc:
                        print(f"❌ Error guardando {output_path}: {exc}")
                        continue

                    print(
                        f"✅ Captura guardada en {output_path}"
                        f" (tamaño {sub_image.shape[1]}x{sub_image.shape[0]} px)."
                    )
                    return True
        finally:  # pragma: no cover - limpieza GUI manual
            cv2.destroyWindow(window_name)

    def _extract_button_region(
        self,
        screenshot: np.ndarray,
        cursor_position: Tuple[int, int],
        descriptor: TargetDescriptor,
    ) -> np.ndarray:
        expected_w, expected_h = descriptor.expected_size or (80, 40)
        margin_x = max(10, expected_w // 4)
        margin_y = max(10, expected_h // 4)

        cx, cy = cursor_position
        x1 = max(0, cx - expected_w // 2 - margin_x)
        y1 = max(0, cy - expected_h // 2 - margin_y)
        x2 = min(screenshot.shape[1], cx + expected_w // 2 + margin_x)
        y2 = min(screenshot.shape[0], cy + expected_h // 2 + margin_y)
        return screenshot[y1:y2, x1:x2]

    def _validate_button_image(
        self, image: np.ndarray, expected_size: Optional[Tuple[int, int]]
    ) -> Tuple[bool, str]:
        if image.size == 0:
            return False, "La región capturada está vacía."

        height, width = image.shape[:2]
        if width < 10 or height < 10:
            return False, "El recorte es demasiado pequeño."

        # Comprobamos variación de color mínima
        if float(np.std(image)) < 2.5:
            return False, "La imagen parece estar en blanco o con pocos detalles."

        if expected_size:
            exp_w, exp_h = expected_size
            tolerance = 0.6
            if not (
                exp_w * (1 - tolerance)
                <= width
                <= exp_w * (1 + tolerance)
            ):
                return False, (
                    f"Ancho inesperado ({width}px). Valor recomendado: ~{exp_w}px."
                )
            if not (
                exp_h * (1 - tolerance)
                <= height
                <= exp_h * (1 + tolerance)
            ):
                return False, (
                    f"Alto inesperado ({height}px). Valor recomendado: ~{exp_h}px."
                )

        return True, ""

    def _handle_existing_button(
        self, existing_path: Path, descriptor: TargetDescriptor
    ) -> bool:
        try:
            current_image = cv2.imread(str(existing_path))
        except Exception as exc:
            print(f"⚠️  No se pudo leer {existing_path}: {exc}")
            return False

        if current_image is None:
            print(f"⚠️  La imagen existente {existing_path.name} es inválida.")
            return False

        valid, message = self._validate_button_image(
            current_image, descriptor.expected_size
        )
        if valid:
            print(
                f"ℹ️  Ya existe una plantilla válida para {descriptor.name}"
                f" ({existing_path.name}, tamaño {current_image.shape[1]}x{current_image.shape[0]} px)."
            )
            if self._prompt_yes_no("¿Deseas conservarla y omitir la captura? [S/n]: "):
                return True
        else:
            print(f"⚠️  La plantilla existente no superó la validación: {message}")

        return False

    # ------------------------------------------------------------------
    # Gestión de ROIs
    # ------------------------------------------------------------------
    def _calibrate_roi(
        self,
        target_id: str,
        descriptor: TargetDescriptor,
        screenshot: np.ndarray,
    ) -> bool:
        window_name = f"Calibrar: {descriptor.name}"
        self.current_screenshot = screenshot
        self.current_selection = None
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self._mouse_callback)

        print("    • Selecciona con el ratón la región rectangular de interés.")
        print("    • Presiona ESPACIO para confirmar, R para refrescar o ESC para omitir.")

        try:
            while True:
                display = self.current_screenshot.copy()
                if self.current_selection:
                    x1, y1, x2, y2 = self.current_selection
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        display,
                        f"{x2 - x1}x{y2 - y1}",
                        (x1, max(y1 - 10, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )
                cv2.imshow(window_name, display)

                key = cv2.waitKey(50) & 0xFF
                if key == 27:  # ESC
                    print("⏭️  Región omitida por el usuario.")
                    return False
                if key == ord("r"):
                    self.current_screenshot = self._capture_screenshot(refresh_notice=True)
                    self.current_selection = None
                if key == 32 and self.current_selection:
                    left, top, right, bottom = self._normalize_selection(
                        self.current_selection
                    )
                    roi_data = {
                        "left": left,
                        "top": top,
                        "width": right - left,
                        "height": bottom - top,
                    }
                    valid, message = self._validate_roi(roi_data, descriptor.expected_size)
                    if not valid:
                        print(f"❌ Selección inválida: {message}")
                        continue

                    self._roi_data[target_id] = roi_data
                    self._roi_settings[target_id] = roi_data
                    print(
                        "✅ ROI registrada:",
                        f"x={roi_data['left']} y={roi_data['top']}",
                        f"w={roi_data['width']} h={roi_data['height']}",
                    )
                    return True
        finally:  # pragma: no cover - limpieza GUI manual
            cv2.destroyWindow(window_name)

    def _mouse_callback(self, event, x, y, flags, param):  # pragma: no cover - GUI
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            self.current_selection = None
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            if not self.start_point:
                return
            x1, y1 = self.start_point
            self.current_selection = (x1, y1, x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            if not self.start_point:
                return
            x1, y1 = self.start_point
            x2, y2 = x, y
            self.current_selection = self._normalize_selection((x1, y1, x2, y2))

    def _normalize_selection(
        self, selection: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = selection
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return left, top, right, bottom

    def _validate_roi(
        self, roi_data: Dict[str, int], expected_size: Optional[Tuple[int, int]]
    ) -> Tuple[bool, str]:
        width = roi_data["width"]
        height = roi_data["height"]
        if width <= 0 or height <= 0:
            return False, "La selección no tiene área."

        if expected_size:
            exp_w, exp_h = expected_size
            tol = 0.7
            if not (exp_w * (1 - tol) <= width <= exp_w * (1 + tol)):
                return False, (
                    f"Ancho inesperado ({width}px). Se esperaba alrededor de {exp_w}px."
                )
            if not (exp_h * (1 - tol) <= height <= exp_h * (1 + tol)):
                return False, (
                    f"Alto inesperado ({height}px). Se esperaba alrededor de {exp_h}px."
                )
        return True, ""

    def _handle_existing_roi(self, target_id: str, descriptor: TargetDescriptor) -> bool:
        roi_data = self._roi_settings.get(target_id)
        if not roi_data:
            return False

        print(
            "ℹ️  ROI existente:",
            f"x={roi_data['left']} y={roi_data['top']} w={roi_data['width']} h={roi_data['height']}",
        )
        valid, message = self._validate_roi(roi_data, descriptor.expected_size)
        if not valid:
            print(f"⚠️  La ROI almacenada no superó la validación: {message}")
            return False

        if self._prompt_yes_no("¿Deseas conservarla y omitir la captura? [S/n]: "):
            self._roi_data[target_id] = roi_data
            return True
        return False

    # ------------------------------------------------------------------
    # Persistencia de ROIs
    # ------------------------------------------------------------------
    def _load_existing_rois(self) -> Dict[str, Dict[str, int]]:
        if not self.settings_path.exists():
            return {}
        try:
            with open(self.settings_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            print(f"⚠️  No se pudo leer {self.settings_path}: {exc}")
            return {}

        vision = data.get("vision", {})
        rois = vision.get("rois", {})
        valid_rois: Dict[str, Dict[str, int]] = {}
        for roi_id, roi_data in rois.items():
            if all(k in roi_data for k in ("left", "top", "width", "height")):
                valid_rois[roi_id] = {
                    "left": int(roi_data["left"]),
                    "top": int(roi_data["top"]),
                    "width": int(roi_data["width"]),
                    "height": int(roi_data["height"]),
                }
        return valid_rois

    def _update_settings_config(self) -> None:
        if not self._roi_data:
            return

        settings = {}
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as fh:
                    settings = json.load(fh)
            except Exception as exc:
                print(f"⚠️  No se pudo leer {self.settings_path}: {exc}")

        settings.setdefault("vision", {}).setdefault("rois", {}).update(self._roi_data)

        try:
            with open(self.settings_path, "w", encoding="utf-8") as fh:
                json.dump(settings, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"⚠️  Error guardando configuración en {self.settings_path}: {exc}")

    # ------------------------------------------------------------------
    # Utilidades varias
    # ------------------------------------------------------------------
    def _capture_screenshot(self, refresh_notice: bool = False) -> np.ndarray:
        if refresh_notice:
            print("🔄  Capturando nueva imagen de pantalla…")
        screenshot = pyautogui.screenshot()
        screenshot_np = np.array(screenshot)
        return cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

    def _prompt_yes_no(self, prompt: str, default: bool = True) -> bool:
        response = input(prompt).strip().lower()
        if not response:
            return default
        return response in {"s", "si", "sí", "y", "yes"}

    def _print_banner(self) -> None:
        print("🎯 Herramienta de Calibración del Blackjack Bot")
        print("=" * 60)
        print(
            "Este asistente capturará las imágenes de referencia necesarias para"
            " el módulo de actuación (M4)."
        )

    # ------------------------------------------------------------------
    # Utilidad de prueba
    # ------------------------------------------------------------------
    def test_calibration(self) -> None:
        print("\n🧪 Probando la detección de las plantillas capturadas…")
        try:
            from m4_actuacion.actuator import Actuator
        except Exception as exc:  # pragma: no cover - import dinámico
            print(f"⚠️  No se pudo importar el actuador para la prueba: {exc}")
            Actuator = None  # type: ignore

        actuator = None
        if Actuator is not None:
            try:
                actuator = Actuator(image_path=str(self.output_dir))
            except Exception as exc:
                print(f"⚠️  No se pudo inicializar el actuador: {exc}")

        if actuator is None:
            print("ℹ️  Se utilizará una detección básica con PyAutoGUI.")

        for target_id, descriptor in self.calibration_config["buttons"].items():
            if not descriptor.filename:
                continue
            template_path = self.output_dir / descriptor.filename
            if not template_path.exists():
                print(f"❌ {descriptor.name}: la plantilla {template_path.name} no existe.")
                continue
            location = None
            if actuator is not None:
                try:
                    location = actuator._find_image_on_screen(
                        descriptor.filename, confidence=0.8
                    )
                except Exception as exc:
                    print(
                        f"⚠️  Error durante la prueba con el actuador de {descriptor.name}: {exc}"
                    )

            if location is None:
                try:
                    location = pyautogui.locateCenterOnScreen(
                        str(template_path), confidence=0.8
                    )
                except pyautogui.ImageNotFoundException:
                    location = None
                except Exception as exc:
                    print(
                        f"⚠️  {descriptor.name}: Error durante la detección básica: {exc}"
                    )
                    continue
            if location:
                print(f"✅ {descriptor.name}: detectado en {location}.")
            else:
                print(f"⚠️  {descriptor.name}: no se encontró en pantalla. Comprueba la captura.")


def main() -> None:
    print("Iniciando herramienta de calibración…")
    print()
    print("INSTRUCCIONES:")
    print("1. Asegúrate de que Caliente.mx esté abierto en tu navegador")
    print("2. Ve a la mesa de All Bets Blackjack y déjala visible")
    print("3. Evita el modo pantalla completa; usa ventana normal")
    print("4. Comprueba que la mesa no esté cubierta por otras ventanas")
    print()
    input("Presiona ENTER para empezar…")

    calibrator = CalibrationTool()
    if calibrator.run_calibration():
        answer = input("\n¿Deseas ejecutar una prueba rápida de detección? [s/N]: ").strip().lower()
        if answer in {"s", "si", "sí", "y", "yes"}:
            calibrator.test_calibration()
    else:
        print("❌ El proceso de calibración no pudo completarse.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProceso interrumpido por el usuario.")
        sys.exit(1)
