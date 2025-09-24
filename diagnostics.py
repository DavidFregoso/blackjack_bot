#!/usr/bin/env python3
"""diagnostics.py - Script de diagnóstico para resolver problemas de ventana."""

from __future__ import annotations

import time
from pathlib import Path

import pyautogui


KEYWORDS = [
    "caliente",
    "chrome",
    "firefox",
    "blackjack",
    "casino",
    "edge",
    "safari",
    "opera",
]


def diagnose_windows() -> bool:
    """Diagnóstico completo de ventanas disponibles."""

    print("\N{LEFT-POINTING MAGNIFYING GLASS} DIAGNÓSTICO DE VENTANAS")
    print("=" * 50)

    # Información del sistema
    try:
        screen_size = pyautogui.size()
        print(
            "\N{STRAIGHT RULER} Resolución de pantalla: "
            f"{screen_size.width}x{screen_size.height}"
        )
    except Exception as exc:  # pragma: no cover - salida informativa
        print(f"\N{CROSS MARK} Error obteniendo resolución: {exc}")

    # Ventana activa actual
    try:
        active_window = pyautogui.getActiveWindow()
        if active_window:
            print(f"\N{DIRECT HIT} Ventana activa: {active_window.title}")
            print(
                "   \N{ROUND PUSHPIN} Posición: "
                f"({active_window.left}, {active_window.top})"
            )
            print(
                "   \N{STRAIGHT RULER} Tamaño: "
                f"{active_window.width}x{active_window.height}"
            )
        else:
            print("\N{WARNING SIGN} No se pudo detectar ventana activa")
    except Exception as exc:  # pragma: no cover - salida informativa
        print(f"\N{CROSS MARK} Error obteniendo ventana activa: {exc}")

    print("\n\N{CLIPBOARD} TODAS LAS VENTANAS DISPONIBLES:")
    print("-" * 50)

    relevant_windows = []
    try:
        all_windows = pyautogui.getAllWindows()
        print(f"Total ventanas encontradas: {len(all_windows)}")

        for i, window in enumerate(all_windows):
            title = window.title or ""
            if len(title.strip()) <= 3:
                continue

            title_lower = title.lower()
            is_relevant = any(keyword in title_lower for keyword in KEYWORDS)
            if is_relevant:
                relevant_windows.append(window)

            status_icons = []
            try:
                if window == pyautogui.getActiveWindow():
                    status_icons.append("\N{DIRECT HIT} ACTIVA")
            except Exception:  # pragma: no cover - tolerancia de entorno
                pass
            if is_relevant:
                status_icons.append("\N{WHITE MEDIUM STAR} RELEVANTE")
            if window.width < 500 or window.height < 400:
                status_icons.append("\N{MOBILE PHONE} PEQUEÑA")
            if not window.visible:
                status_icons.append("\N{GHOST} OCULTA")

            status = " ".join(status_icons) if status_icons else "  "

            print(f"{i + 1:3d}. {status}")
            print(f"     \N{MEMO} Título: {title[:70]}")
            print(f"     \N{STRAIGHT RULER} Tamaño: {window.width}x{window.height}")
            print(f"     \N{ROUND PUSHPIN} Posición: ({window.left}, {window.top})")
            print()

            if i >= 20:
                print("... (mostrando solo las primeras 20 ventanas)")
                break

    except Exception as exc:  # pragma: no cover - salida informativa
        print(f"\N{CROSS MARK} Error listando ventanas: {exc}")

    print(
        f"\n\N{WHITE MEDIUM STAR} VENTANAS RELEVANTES ENCONTRADAS: "
        f"{len(relevant_windows)}"
    )

    print("\n\N{LEFT-POINTING MAGNIFYING GLASS} PROBANDO MÉTODOS DE BÚSQUEDA:")
    print("-" * 50)

    search_terms = ["Caliente", "Chrome", "All Bets", "Blackjack"]
    for term in search_terms:
        try:
            windows = pyautogui.getWindowsWithTitle(term)
            print(f"'{term}': {len(windows)} ventanas encontradas")
            for window in windows[:3]:
                print(f"  → {window.title}")
        except Exception as exc:  # pragma: no cover - salida informativa
            print(f"'{term}': Error - {exc}")

    return bool(relevant_windows)


def test_window_activation() -> bool:
    """Prueba activar ventanas relevantes."""

    print("\n\N{VIDEO GAME} PRUEBA DE ACTIVACIÓN DE VENTANAS")
    print("=" * 50)

    search_terms = ["Caliente", "Chrome", "Firefox", "Edge"]
    for term in search_terms:
        try:
            windows = pyautogui.getWindowsWithTitle(term)
            if not windows:
                print(f"\N{CROSS MARK} {term}: No encontrado")
                continue

            print(f"\n\N{DIRECT HIT} Intentando activar: {term}")
            target = windows[0]
            print(f"   Título completo: {target.title}")

            target.activate()
            time.sleep(2)

            current_active = pyautogui.getActiveWindow()
            if current_active and current_active.title == target.title:
                print("   \N{WHITE HEAVY CHECK MARK} Activación exitosa")
                return True

            print("   \N{WARNING SIGN} No se pudo confirmar activación")

        except Exception as exc:  # pragma: no cover - salida informativa
            print(f"\N{CROSS MARK} {term}: Error - {exc}")

    return False


def check_prerequisites() -> bool:
    """Verifica los prerequisitos del sistema."""

    print("\n\N{WRENCH} VERIFICACIÓN DE PREREQUISITOS")
    print("=" * 50)

    # Verificar pyautogui
    try:
        version = pyautogui.__version__
        print(f"\N{WHITE HEAVY CHECK MARK} PyAutoGUI versión: {version}")
    except Exception as exc:  # pragma: no cover - salida informativa
        print(f"\N{CROSS MARK} PyAutoGUI: Error - {exc}")
        return False

    try:
        print(f"\N{LOCK} FAILSAFE activo: {pyautogui.FAILSAFE}")
        if pyautogui.FAILSAFE:
            print(
                "   \N{ELECTRIC LIGHT BULB} Tip: Mueve el mouse a la esquina "
                "superior izquierda para activar FAILSAFE"
            )
    except Exception:  # pragma: no cover - salida informativa
        pass

    dirs_to_check = [
        "m4_actuacion/target_images",
        "configs",
        "logs",
    ]

    for dir_path in dirs_to_check:
        path = Path(dir_path)
        if path.exists():
            print(f"\N{WHITE HEAVY CHECK MARK} Directorio: {dir_path}")
        else:
            print(f"\N{CROSS MARK} Directorio faltante: {dir_path}")

    return True


def main() -> None:
    """Función principal de diagnóstico."""

    print("\N{STAFF OF AESCULAPIUS} DIAGNÓSTICO COMPLETO DEL SISTEMA")
    print("=" * 60)
    print()

    if not check_prerequisites():
        print("\N{CROSS MARK} Faltan prerequisitos básicos")
        return

    has_relevant_windows = diagnose_windows()

    if has_relevant_windows:
        activation_success = test_window_activation()

        print("\n\N{BAR CHART} RESUMEN DEL DIAGNÓSTICO")
        print("=" * 50)
        print(
            "\N{WHITE HEAVY CHECK MARK} Ventanas relevantes encontradas: "
            f"{'Sí' if has_relevant_windows else 'No'}"
        )
        print(
            "\N{WHITE HEAVY CHECK MARK} Activación de ventana: "
            f"{'Exitosa' if activation_success else 'Fallida'}"
        )

        if has_relevant_windows and activation_success:
            print("\n\N{PARTY POPPER} SISTEMA LISTO PARA CALIBRACIÓN")
            print("Puedes ejecutar: python calibration_tool.py")
        else:
            print("\n\N{WARNING SIGN} RECOMENDACIONES:")
            if not has_relevant_windows:
                print("  • Abre Caliente.mx en tu navegador")
                print("  • Navega a la mesa de All Bets Blackjack")
                print("  • Asegúrate de que la ventana sea visible")
            if not activation_success:
                print("  • Cierra otras aplicaciones que puedan interferir")
                print("  • Ejecuta este script como administrador (Windows)")
                print("  • Verifica que no haya ventanas modales abiertas")
    else:
        print("\n\N{CROSS MARK} NO SE ENCONTRARON VENTANAS RELEVANTES")
        print("\nSOLUCIONES:")
        print("  1. Abre tu navegador web")
        print("  2. Ve a https://caliente.mx")
        print("  3. Inicia sesión en tu cuenta")
        print("  4. Navega a 'Casino' → 'All Bets Blackjack'")
        print("  5. Asegúrate de que la ventana esté visible (no minimizada)")
        print("  6. Ejecuta este diagnóstico nuevamente")


if __name__ == "__main__":  # pragma: no cover - ejecución directa
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n\N{BLACK SQUARE FOR STOP} Diagnóstico cancelado")
    except Exception as exc:  # pragma: no cover - salida informativa
        print(f"\n\N{COLLISION SYMBOL} Error inesperado: {exc}")
        print("\nSi el problema persiste, reporta este error junto con:")
        print("  • Tu sistema operativo y versión")
        print("  • Navegador que utilizas")
        print("  • Si tienes múltiples monitores")
