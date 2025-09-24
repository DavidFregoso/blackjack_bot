"""Herramienta interactiva para capturar y calibrar imágenes objetivo del módulo M4.

Esta utilidad guía al operador paso a paso para crear las plantillas que utiliza el
actuador del bot de Blackjack. Se incluyen ayudas visuales, validaciones automáticas
y manejo básico de errores para evitar configuraciones inconsistentes.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

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

        self.calibration_config: Dict[str, Dict[str, TargetDescriptor]] = {
            "buttons": {
                "hit_button": TargetDescriptor(
                    name="Botón PEDIR / HIT",
                    filename="hit_button.png",
                    description="Botón verde '+' para pedir carta",
                    expected_size=(80, 40),
                ),
                "stand_button": TargetDescriptor(
                    name="Botón PLANTARSE / STAND",
                    filename="stand_button.png",
                    description="Botón rojo 'Ø' para plantarse",
                    expected_size=(80, 40),
                ),
                "double_button": TargetDescriptor(
                    name="Botón DOBLAR / DOUBLE",
                    filename="double_button.png",
                    description="Botón amarillo 'x2' para doblar",
                    expected_size=(80, 40),
                ),
                "chip_25": TargetDescriptor(
                    name="Ficha de 25",
                    filename="chip_25.png",
                    description="Ficha de valor 25 (habitualmente color rojo o verde)",
                    expected_size=(50, 50),
                ),
                "chip_100": TargetDescriptor(
                    name="Ficha de 100",
                    filename="chip_100.png",
                    description="Ficha de valor 100 (habitualmente color negro)",
                    expected_size=(50, 50),
                ),
            },
            "rois": {
                "bankroll_area": TargetDescriptor(
                    name="Área del bankroll",
                    description="Región donde aparece el saldo actual del jugador",
                    expected_size=(150, 30),
                ),
            },
        }

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------
    def run_calibration(self) -> bool:
        """Ejecuta el proceso completo de calibración."""
        self._print_banner()

        print("\n🔍 Detectando ventana del juego…")
        self._show_available_windows()

        if not self._verify_game_window():
            print("\n⚠️  No se pudo detectar automáticamente la ventana del juego.")
            print("Asegúrate de que:")
            print("  1. Caliente.mx esté abierto en tu navegador")
            print("  2. La mesa de Blackjack esté visible y activa")
            print("  3. La ventana no esté minimizada ni cubierta por otras aplicaciones")

            if not self._prompt_yes_no("¿Quieres continuar de todas formas? [s/N]: ", default=False):
                return False

        print("\n🔘 Calibrando botones de acción…")
        for target_id, descriptor in self.calibration_config["buttons"].items():
            if not self._calibrate_target(target_id, descriptor, target_type="button"):
                print(f"⚠️  Se omitió la calibración de {descriptor.name}.")

        print("\n🔍 Calibrando regiones de interés…")
        for target_id, descriptor in self.calibration_config["rois"].items():
            if not self._calibrate_target(target_id, descriptor, target_type="roi"):
                print(f"⚠️  Se omitió la calibración de {descriptor.name}.")

        self._update_settings_config()
        print("\n✅ Calibración completada.")
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

    def _show_available_windows(self) -> None:
        """Muestra una lista de ventanas relevantes detectadas por el sistema."""
        try:
            all_windows = pyautogui.getAllWindows()
        except Exception as exc:
            print(f"⚠️  Error listando ventanas disponibles: {exc}")
            return

        print("\n📋 Ventanas detectadas:")
        relevant_keywords = [
            "caliente",
            "blackjack",
            "casino",
            "chrome",
            "firefox",
            "edge",
            "safari",
        ]

        relevant_windows = []
        for window in all_windows:
            title = getattr(window, "title", "") or ""
            if not title.strip():
                continue
            lowered = title.lower()
            if any(keyword in lowered for keyword in relevant_keywords):
                relevant_windows.append(window)

        if not relevant_windows:
            print("  ❌ No se encontraron ventanas relevantes.")
            return

        try:
            active_window = pyautogui.getActiveWindow()
        except Exception:
            active_window = None

        for idx, window in enumerate(relevant_windows[:10], start=1):
            is_active = active_window is not None and window == active_window
            status = "✅ ACTIVA" if is_active else "  "
            title = getattr(window, "title", "")
            width = getattr(window, "width", "?")
            height = getattr(window, "height", "?")
            left = getattr(window, "left", "?")
            top = getattr(window, "top", "?")
            print(f"  {idx:2d}. {status} {title[:60]}")
            print(f"      📐 Tamaño: {width}x{height}, Posición: ({left}, {top})")

    def _verify_game_window(self) -> bool:
        print("🔍 Buscando la ventana del juego 'All Bets Blackjack'…")
        search_patterns = [
            "Caliente",
            "All Bets Blackjack",
            "Blackjack",
            "Chrome",
            "Firefox",
            "Edge",
        ]

        try:
            for pattern in search_patterns:
                try:
                    windows = pyautogui.getWindowsWithTitle(pattern)
                except Exception as exc:
                    print(f"⚠️  Error al buscar ventanas con el patrón '{pattern}': {exc}")
                    continue

                if not windows:
                    continue

                target_window = windows[0]
                try:
                    target_window.activate()
                    time.sleep(1)
                except Exception as exc:
                    print(
                        f"⚠️  No se pudo activar la ventana coincidente con '{pattern}': {exc}"
                    )
                    continue

                title = getattr(target_window, "title", pattern)
                print(f"✅ Ventana encontrada y activada: {title}")
                return True

            print(
                "❌ No se encontró la ventana del juego de forma automática."
            )
            return False
        except Exception as exc:
            print(f"⚠️  Error al verificar la ventana: {exc}")
            return False

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
