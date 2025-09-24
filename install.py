#!/usr/bin/env python3
"""
install.py - Script de instalación automática del Blackjack Bot
Ejecutar: python install.py
"""

import subprocess
import sys
import os
import platform
from pathlib import Path

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
        result = subprocess.run(command, shell=True, check=True, 
                              capture_output=True, text=True)
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

def install_tesseract():
    """Instala Tesseract OCR según el sistema operativo"""
    system = detect_platform()
    
    if system == "windows":
        print("   📋 WINDOWS - Instalación manual requerida:")
        print("   1. Descargar: https://github.com/UB-Mannheim/tesseract/wiki")
        print("   2. Instalar en: C:\\Program Files\\Tesseract-OCR\\")
        print("   3. Agregar al PATH del sistema")
        input("   ⏳ Presiona ENTER cuando hayas completado la instalación...")
        
    elif system == "darwin":  # macOS
        if run_command("which brew", "Verificando Homebrew", critical=False):
            run_command("brew install tesseract", "Instalando Tesseract via Homebrew")
        else:
            print("   📋 macOS - Opciones de instalación:")
            print("   1. Instalar Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
            print("   2. Luego ejecutar: brew install tesseract")
            input("   ⏳ Presiona ENTER cuando hayas completado la instalación...")
            
    elif system == "linux":
        # Detectar distribución
        if Path("/etc/apt/sources.list").exists():  # Debian/Ubuntu
            run_command("sudo apt-get update", "Actualizando paquetes")
            run_command("sudo apt-get install -y tesseract-ocr", "Instalando Tesseract")
        elif Path("/etc/redhat-release").exists():  # RedHat/CentOS
            run_command("sudo yum install -y tesseract", "Instalando Tesseract")
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
        "configs"
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
    
    # Probar Tesseract específicamente
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("   ✅ Tesseract OCR funcionando")
    except:
        print("   ❌ Tesseract OCR no funciona correctamente")
        return False
    
    return True

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
    run_command(f'"{sys.executable}" -m pip install --upgrade pip',
                "Actualizando pip")
    run_command(f'"{sys.executable}" -m pip install -r requirements.txt',
                "Instalando dependencias desde requirements.txt")
    
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
