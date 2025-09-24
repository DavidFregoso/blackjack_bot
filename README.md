Aviso: Proyecto educativo para simulador/UI propia. No usar en plataformas de apuestas reales ni para evadir Términos de Servicio.

🚀 Instalación Rápida (3 comandos)
# 1) Clonar el repositorio
git clone https://github.com/DavidFregoso/blackjack_bot.git
cd blackjack-bot


# 2) Instalar dependencias
pip install -r requirements.txt


# 3) Ejecutar instalación automática
python install.py
📋 Requisitos del Sistema

Mínimos

Python 3.8 o superior

RAM: 4 GB (recomendado 8 GB)

Disco: 2 GB libres

Resolución mínima: 1920×1080

Internet para descargar dependencias

Sistemas Operativos Soportados

✅ Windows 10/11 (64-bit)

✅ macOS 10.14+ (Intel/Apple Silicon)

✅ Linux (Ubuntu 18.04+, CentOS 7+, Debian 9+)

🛠 Instalación Detallada
Opción A — Automática (recomendada)
git clone https://github.com/tu-usuario/blackjack-bot.git
cd blackjack-bot
python install.py
Opción B — Manual

Verificar Python

python --version

Instalar dependencias

pip install -r requirements.txt

Instalar Tesseract OCR

Windows: Descargar https://github.com/UB-Mannheim/tesseract/wiki · Ruta sugerida C:\Program Files\Tesseract-OCR\ · Agregar al PATH

macOS: brew install tesseract

Linux (Ubuntu/Debian): sudo apt-get install tesseract-ocr

Crear directorios

python -c "
from pathlib import Path
for d in ['m4_actuacion/target_images','m1_ingesta/templates/ranks','m1_ingesta/templates/suits','logs','configs']:
    Path(d).mkdir(parents=True, exist_ok=True)
print('Directorios creados')
"
🎮 Guía de Uso

Paso 1 — Simulador

Usa tu simulador/UI propia. Ventana no a pantalla completa, esquina superior izquierda del monitor.

Paso 2 — Calibración

python calibration_tool.py

Controles: ESPACIO (capturar), ESC (omitir), R (actualizar).

Paso 3 — Configuración Edita configs/decision.json (riesgo, rampa, límites), configs/settings.json (ROIs, umbrales) y configs/emergency_settings.json (seguridad).

Paso 4 — Iniciar

python live_bot_app.py      # directo
start_bot.bat               # Windows
./start_bot.sh              # macOS/Linux

Paso 5 — Panel web

Abre http://localhost:5000 para TC, bankroll, decisiones y logs.

📊 Módulos

M1 Visión: OCR, cartas, fases.

M2 Cerebro: Hi‑Lo y Zen, True Count, FSM.

M3 Decisiones: Estrategia básica, Illustrious 18/Fab 4, rampa y stops.

M4 Actuación: Detección de botones, mouse natural, verificación post‑acción, paradas.

M5 Métricas: Logging JSONL, dashboard, replay, health.

🐛 Solución de Problemas

“Ventana no encontrada”

python -c "import pyautogui; print([w.title for w in pyautogui.getAllWindows()])"

“OCR no funciona”

python -c "import pytesseract; print(pytesseract.get_tesseract_version())"

“No encuentra botones”

python calibration_tool.py

Logs y verificación

tail -f logs/session_*.jsonl
python verification_script.py
python analysis_app.py
⚖️ Legal y Ética

Uso académico/investigación, sin garantías.

No automatizar ni interactuar con sitios de apuestas reales.

Respeta ToS y regulaciones locales.

📚 Recursos

Libros: Thorp (Beat the Dealer), Wong (Professional Blackjack), Renzey (Blackjack Bluebook II).

Sitios: BlackjackApprenticeship.com, BJA Basic Strategy Trainer, CVData Simulators.

🏆 Créditos

BlueberriesLab — Fundadores: David Fregoso, Alfredo López Avelar y Jesús Alejandro Ocegueda.
Agradecimientos a la comunidad por las aportaciones en visión por computadora, OCR y automatización.

Referencias conceptuales:

Hi‑Lo (Harvey Dubner), Illustrious 18 (Don Schlesinger), Zen Count (Arnold Snyder).

Simulaciones y estrategia básica inspiradas en trabajos clásicos.

Tecnologías: OpenCV, Tesseract, Flask, PyAutoGUI.

📄 Licencia

Código abierto con fines educativos bajo Licencia MIT.
Copyright (c) 2025 BlueberriesLab — Fundadores: David Fregoso, Alfredo López Avelar, Jesús Alejandro Ocegueda.
Consulta el archivo LICENSE.
