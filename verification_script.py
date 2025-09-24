#!/usr/bin/env python3
"""Script de verificación antes de ejecutar el bot.

Realiza comprobaciones básicas de entorno, recursos gráficos y dependencias.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import cv2  # noqa: F401 - utilizado para verificar disponibilidad de OpenCV
import pyautogui

if importlib.util.find_spec("pytesseract"):
    import pytesseract
else:  # pragma: no cover - depende de la instalación
    pytesseract = None  # type: ignore

if importlib.util.find_spec("PIL.Image"):
    from PIL import Image
else:  # pragma: no cover - depende de la instalación
    Image = None  # type: ignore


def pre_flight_check() -> bool:
    """Verificaciones críticas antes del lanzamiento."""
    checks = {
        "game_window": False,
        "target_images": False,
        "config_files": False,
        "ocr_working": False,
        "screen_resolution": False,
    }

    print("🔍 Ejecutando verificaciones pre-vuelo...")

    # 1. Verificar ventana del juego
    try:
        windows = pyautogui.getWindowsWithTitle("Caliente")
        if windows:
            checks["game_window"] = True
            print("✅ Ventana del juego encontrada")
        else:
            print("❌ Ventana del juego NO encontrada")
    except Exception:
        print("❌ Error verificando ventana del juego")

    # 2. Verificar imágenes objetivo
    target_dir = Path("m4_actuacion/target_images/")
    required_images = ["hit_button.png", "stand_button.png", "double_button.png"]

    missing_images = [img for img in required_images if not (target_dir / img).exists()]
    if not missing_images:
        checks["target_images"] = True
        print("✅ Todas las imágenes objetivo encontradas")
    else:
        print(f"❌ Imágenes faltantes: {missing_images}")

    # 3. Verificar archivos de configuración
    config_files = [
        "configs/settings.json",
        "configs/decision.json",
        "configs/emergency_settings.json",
    ]
    missing_configs = [cfg for cfg in config_files if not Path(cfg).exists()]
    if not missing_configs:
        checks["config_files"] = True
        print("✅ Archivos de configuración encontrados")
    else:
        print(f"❌ Configuraciones faltantes: {missing_configs}")

    # 4. Verificar OCR
    if pytesseract and Image:
        try:
            sample = Image.new("RGB", (60, 20), color="white")
            pytesseract.image_to_string(sample)
            checks["ocr_working"] = True
            print("✅ OCR funcionando")
        except Exception:
            print("❌ OCR no funciona - verificar instalación de Tesseract")
    else:
        print("❌ OCR no disponible - instalar pytesseract y PIL")

    # 5. Verificar resolución de pantalla
    try:
        screen_size = pyautogui.size()
        if screen_size.width >= 1920 and screen_size.height >= 1080:
            checks["screen_resolution"] = True
            print("✅ Resolución de pantalla adecuada")
        else:
            print(f"⚠️ Resolución baja: {screen_size} - puede afectar detección")
            checks["screen_resolution"] = True
    except Exception:
        print("❌ No se pudo determinar la resolución de pantalla")

    passed = sum(1 for value in checks.values() if value)
    total = len(checks)

    print(f"\n📊 Resultado: {passed}/{total} verificaciones pasadas")

    if passed == total:
        print("🟢 SISTEMA LISTO PARA EJECUTAR")
        return True

    print("🔴 SISTEMA NO LISTO - Corregir errores antes de continuar")
    return False
if __name__ == "__main__":
    pre_flight_check()
