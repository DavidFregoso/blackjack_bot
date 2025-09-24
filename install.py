#!/usr/bin/env python3
"""
install.py - Script de instalación automática del Blackjack Bot
Ejecutar: python install.py
"""

import subprocess
import sys
import os
import platform
import shutil
from pathlib import Path

from utils import tesseract_helper


def print_step(message, step_num=None):
    """Imprime un paso de instalación con formato"""
    if step_num:
        print(f"\n{'='*60}")
        print(f"🔧 PASO {step_num}: {message}")
        print(f"{'='*60}")
    else:
        print(f"   {message}")


def run_command(command, description, critical=True):
    """Ejecuta un comando del sistema"""
    print(f"   ▶️ {description}")
    print(f"   💻 Ejecutando: {command}")

    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True
        )
        print(f"   ✅ {description} - Completado")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error en: {description}")
        print(f"   📋 Output: {e.stdout}")
        print(f"   ❗ Error: {e.stderr}")
        if critical:
            print(f"\n🚨 INSTALACIÓN FALLIDA - Error crítico")
            sys.exit(1)
        return False


def check_python_version():
    """Verifica la versión de Python"""
    version = sys.version_info
    print(f"   🐍 Python detectado: {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("   ❌ Se requiere Python 3.8 o superior")
        print("   📥 Descarga desde: https://www.python.org/downloads/")
        sys.exit(1)
    else:
        print("   ✅ Versión de Python compatible")


def detect_platform():
    """Detecta el sistema operativo"""
    system = platform.system().lower()
    print(f"   💻 Sistema operativo: {system}")
    return system


def _command_available(command: str) -> bool:
    """Comprueba si un comando existe en el entorno actual."""

    return shutil.which(command) is not None


def _prompt_yes_no(message: str, default: bool = True) -> bool:
    """Solicita confirmación al usuario con una respuesta sí/no."""

    prompt = " [S/n]: " if default else " [s/N]: "
    valid_yes = {"s", "si", "sí", "y", "yes"}
    valid_no = {"n", "no"}

    while True:
        response = input(f"   {message}{prompt}").strip().lower()
        if not response:
            return default
        if response in valid_yes:
            return True
        if response in valid_no:
            return False
        print("   🔁 Responde con 's' o 'n'.")


def _post_installation_check(origin: str) -> bool:
    """Verifica si Tesseract quedó instalado tras ejecutar un instalador."""

    configured, executable, source = tesseract_helper.configure_pytesseract()
    if configured and executable:
        detected_from = source or origin
        print(f"   ✅ Tesseract detectado ({detected_from}: {executable})")
        shell_hint = "PowerShell" if platform.system().lower() == "windows" else "la terminal"
        print(
            f"   📌 Si el comando 'tesseract --version' no funciona aún, abre una nueva ventana de {shell_hint}."
        )
        return True

    print("   ⚠️ No se detectó automáticamente Tesseract tras la instalación.")
    print(
        "   💡 Puedes proporcionar la ruta manualmente cuando se te solicite o reiniciar la terminal."
    )
    return False


def _print_windows_manual_instructions() -> None:
    """Muestra las instrucciones manuales de instalación para Windows."""

    print("   📋 WINDOWS - Instalación manual:")
    print("   1. Descargar: https://github.com/UB-Mannheim/tesseract/wiki")
    print("   2. Instalar en: C:/Program Files/Tesseract-OCR/")
    print("   3. Asegurarte de que la opción 'Add to PATH' esté marcada")
    print("   4. Si no quedó en el PATH, agrega la carpeta con:")
    print("      setx PATH \"$($env:PATH);C:\\Program Files\\Tesseract-OCR\\\"")
    print("   5. Cierra y vuelve a abrir PowerShell, luego ejecuta: tesseract --version")
    print(
        "   📚 Para soporte en español, copia 'spa.traineddata' en C:/Program Files/Tesseract-OCR/tessdata/"
    )
    input("   ⏳ Presiona ENTER cuando hayas completado la instalación...")


def _install_tesseract_windows() -> bool:
    """Gestiona la instalación de Tesseract en sistemas Windows."""

    installed = False

    if _command_available("winget"):
        print("   📦 Winget detectado en el sistema.")
        if _prompt_yes_no("¿Deseas instalar Tesseract automáticamente con winget?", True):
            installed = run_command(
                "winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements",
                "Instalando Tesseract con winget",
                critical=False,
            )
            if installed and _post_installation_check("winget"):
                return True

    if not installed and _command_available("choco"):
        print("   📦 Chocolatey detectado en el sistema.")
        if _prompt_yes_no("¿Deseas instalar Tesseract automáticamente con Chocolatey?", True):
            installed = run_command(
                "choco install tesseract --yes",
                "Instalando Tesseract con Chocolatey",
                critical=False,
            )
            if installed and _post_installation_check("chocolatey"):
                return True

    _print_windows_manual_instructions()
    return _post_installation_check("instalación manual")


def install_tesseract():
    """Instala Tesseract OCR según el sistema operativo"""

    system = detect_platform()

    configured, executable, source = tesseract_helper.configure_pytesseract()
    if configured and executable:
        origin = source or "ruta detectada"
        print(f"   ✅ Tesseract ya se encuentra instalado ({origin}: {executable})")
        return

    if system == "windows":
        if _install_tesseract_windows():
            return

    elif system == "darwin":  # macOS
        if run_command("which brew", "Verificando Homebrew", critical=False):
            if run_command("brew install tesseract", "Instalando Tesseract via Homebrew", critical=False):
                _post_installation_check("homebrew")
        else:
            print("   📋 macOS - Opciones de instalación:")
            print(
                '   1. Instalar Homebrew: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            )
            print("   2. Luego ejecutar: brew install tesseract")
            input("   ⏳ Presiona ENTER cuando hayas completado la instalación...")

    elif system == "linux":
        # Detectar distribución
        if Path("/etc/apt/sources.list").exists():  # Debian/Ubuntu
            if run_command("sudo apt-get update", "Actualizando paquetes", critical=False):
                installed = run_command(
                    "sudo apt-get install -y tesseract-ocr",
                    "Instalando Tesseract",
                    critical=False,
                )
                if installed:
                    _post_installation_check("apt")
        elif Path("/etc/redhat-release").exists():  # RedHat/CentOS
            installed = run_command(
                "sudo yum install -y tesseract",
                "Instalando Tesseract",
                critical=False,
            )
            if installed:
                _post_installation_check("yum")
        else:
            print("   📋 LINUX - Instalar manualmente:")
            print("   Ubuntu/Debian: sudo apt-get install tesseract-ocr")
            print("   CentOS/RHEL: sudo yum install tesseract")
            input("   ⏳ Presiona ENTER cuando hayas completado la instalación...")



def create_directories():
    """Crea la estructura de directorios necesaria"""
    directories = [
        "m4_actuacion/target_images",
        "m1_ingesta/templates/ranks",
        "m1_ingesta/templates/suits",
        "logs",
        "configs",
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"   📁 Creado: {directory}")


def create_startup_scripts():
    """Crea scripts de inicio para diferentes sistemas"""

    # Script para Windows
    windows_script = """@echo off
echo 🎰 Iniciando Blackjack Bot...
echo ================================
python live_bot_app.py
pause
"""

    with open("start_bot.bat", "w", encoding="utf-8") as f:
        f.write(windows_script)

    # Script para Unix/Linux/macOS
    unix_script = """#!/bin/bash
echo "🎰 Iniciando Blackjack Bot..."
echo "================================"
python3 live_bot_app.py
read -p "Presiona ENTER para cerrar..."
"""

    with open("start_bot.sh", "w", encoding="utf-8") as f:
        f.write(unix_script)

    # Hacer ejecutable en Unix
    try:
        os.chmod("start_bot.sh", 0o755)
    except:
        pass

    print("   📜 Scripts de inicio creados: start_bot.bat, start_bot.sh")


def test_installation():
    """Prueba la instalación"""
    print("   🧪 Probando dependencias...")

    test_imports = [
        ("flask", "Flask web framework"),
        ("cv2", "OpenCV para visión por computadora"),
        ("numpy", "NumPy para cálculos numéricos"),
        ("PIL", "Pillow para procesamiento de imágenes"),
        ("pyautogui", "PyAutoGUI para automatización"),
        ("pytesseract", "Tesseract OCR"),
    ]

    failed_imports = []

    for module, description in test_imports:
        try:
            __import__(module)
            print(f"   ✅ {description}")
        except ImportError:
            print(f"   ❌ {description}")
            failed_imports.append(module)

    if failed_imports:
        print(f"\n   ⚠️ Módulos fallidos: {', '.join(failed_imports)}")
        return False

    return verify_tesseract_installation()


def _relative_path(path: Path) -> str:
    """Devuelve una representación amigable de una ruta."""

    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _prompt_manual_tesseract_configuration() -> bool:
    """Permite que la persona usuaria introduzca manualmente la ruta a Tesseract."""

    print("   📥 Proporciona la ruta al ejecutable de Tesseract si ya lo instalaste.")
    print("   💡 Ejemplo: C:/Program Files/Tesseract-OCR/tesseract.exe")
    print(
        "   💡 Puedes indicar la carpeta y el asistente completará el nombre del ejecutable."
    )
    print("   💡 Deja el campo vacío para omitir este paso.")

    while True:
        user_input = input("   Ruta a Tesseract (ENTER para omitir): ").strip()
        if not user_input:
            print("   ⚠️ Se omitió la configuración manual de Tesseract.")
            return False

        candidate = tesseract_helper.validate_tesseract_path(user_input)
        if candidate is None:
            print(
                "   ❌ No se encontró un ejecutable válido en la ruta indicada. Intenta nuevamente."
            )
            continue

        stored_path = tesseract_helper.store_tesseract_path(candidate)
        configured, _, _ = tesseract_helper.configure_pytesseract()
        if configured:
            print(
                f"   ✅ Ruta guardada en { _relative_path(tesseract_helper.TESSERACT_PATH_FILE) }"
            )
            print(f"   🔧 Tesseract configurado desde: {stored_path}")
            return True

        print("   ❌ No fue posible configurar Tesseract con la ruta proporcionada.")
        print("   🔁 Verifica los permisos del archivo e inténtalo nuevamente.")


def verify_tesseract_installation():
    """Verifica y configura Tesseract si es necesario."""

    try:
        import pytesseract
    except ImportError:
        print("   ❌ Tesseract OCR no funciona correctamente")
        print("   📋 El paquete 'pytesseract' no está instalado.")
        return False

    configured, executable_path, source = tesseract_helper.configure_pytesseract()

    try:
        version = pytesseract.get_tesseract_version()
        print(f"   ✅ Tesseract OCR funcionando (versión {version})")

        if executable_path:
            source_msg = source or "ruta detectada"
            print(f"   ℹ️ {source_msg.capitalize()}: {executable_path}")
            if source != "system PATH":
                print(
                    "   🔧 Se añadió temporalmente esta ruta al PATH de la sesión actual."
                )
                print(
                    "   📌 Agrega la carpeta de Tesseract al PATH del sistema para evitar futuros problemas."
                )

        return True
    except (pytesseract.TesseractNotFoundError, FileNotFoundError) as error:
        print("   ❌ Tesseract OCR no funciona correctamente")
        if executable_path:
            print(f"   📋 Se intentó usar: {executable_path}")
        else:
            print("   🔎 No se encontró el ejecutable 'tesseract' en el sistema.")

        system = platform.system().lower()
        if system == "windows":
            print(
                "   👉 Verifica que Tesseract esté instalado en 'C:/Program Files/Tesseract-OCR/' y que la carpeta esté en el PATH."
            )
        elif system == "darwin":
            print("   👉 Instala Tesseract con Homebrew: brew install tesseract")
        else:
            print(
                "   👉 Instala Tesseract con el gestor de paquetes de tu distribución (por ejemplo, sudo apt-get install tesseract-ocr)."
            )

        print(f"   ❗ Detalle: {error}")

        manual_configured = _prompt_manual_tesseract_configuration()
        if manual_configured:
            try:
                version = pytesseract.get_tesseract_version()
                print(f"   ✅ Tesseract OCR funcionando (versión {version})")
                return True
            except Exception as retry_error:
                print("   ❌ Tesseract sigue sin responder correctamente")
                print(f"   ❗ Detalle: {retry_error}")

        return False
    except Exception as error:
        print("   ❌ Ocurrió un error al verificar Tesseract OCR")
        print(f"   ❗ Detalle: {error}")
        return False


def main():
    """Función principal de instalación"""
    print("🎰 INSTALADOR DEL BLACKJACK BOT v1.0")
    print("=====================================\n")

    # Paso 1: Verificar Python
    print_step("Verificando Python", 1)
    check_python_version()

    # Paso 2: Crear directorios
    print_step("Creando estructura de directorios", 2)
    create_directories()

    # Paso 3: Instalar dependencias de Python
    print_step("Instalando dependencias de Python", 3)
    run_command(f'"{sys.executable}" -m pip install --upgrade pip', "Actualizando pip")
    run_command(
        f'"{sys.executable}" -m pip install -r requirements.txt',
        "Instalando dependencias desde requirements.txt",
    )

    # Paso 4: Instalar Tesseract OCR
    print_step("Instalando Tesseract OCR", 4)
    install_tesseract()

    # Paso 5: Crear scripts de inicio
    print_step("Creando scripts de inicio", 5)
    create_startup_scripts()

    # Paso 6: Probar instalación
    print_step("Probando instalación", 6)
    if test_installation():
        print("\n🎉 INSTALACIÓN COMPLETADA EXITOSAMENTE!")
        print("=" * 60)
        print("📋 PRÓXIMOS PASOS:")
        print("1. Abrir el juego 'All Bets Blackjack' en tu navegador")
        print("2. Ejecutar calibración: python calibration_tool.py")
        print("3. Iniciar el bot: python live_bot_app.py")
        print("4. Abrir interfaz web: http://localhost:5000")
        print("\n🚀 ¡Todo listo para empezar!")
    else:
        print("\n⚠️ INSTALACIÓN COMPLETADA CON ADVERTENCIAS")
        print("Algunos componentes pueden no funcionar correctamente.")
        print("Revisa los mensajes de error arriba.")


if __name__ == "__main__":
    main()
