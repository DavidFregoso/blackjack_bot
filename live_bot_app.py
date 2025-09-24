from flask import Flask, render_template, request
from flask_socketio import SocketIO
import threading
import time
import json
import pyautogui

# Importa todos tus módulos
from m1_ingesta.vision_system import VisionSystem, RegionOfInterest
from m2_cerebro.contador import CardCounter
from m2_cerebro.fsm import GameFSM
from m3_decision.orquestador import DecisionOrchestrator
from m4_actuacion.actuator import Actuator
from m5_metricas.logger import EventLogger

# --- Configuración de la WebApp ---
app = Flask(__name__, template_folder='frontend')
socketio = SocketIO(app, async_mode='eventlet')
bot_thread = None
bot_running = False

# --- El Motor del Bot ---
def bot_worker(config):
    global bot_running
    print("🤖 Hilo del Bot iniciado con la configuración:", config)
    
    # --- Inicialización de Módulos ---
    logger = EventLogger()
    actuator = Actuator()
    
    # Lógica para encontrar la ventana del juego
    try:
        game_windows = pyautogui.getWindowsWithTitle("Caliente.mx")
        if not game_windows:
            socketio.emit('status_update', {'log': "ERROR: No se encontró la ventana del juego 'Caliente.mx'.", 'status': 'Error'})
            bot_running = False
            return
        game_window = game_windows[0]
        print(f"Ventana del juego encontrada: {game_window.title}")
    except Exception as e:
        socketio.emit('status_update', {'log': f"ERROR al buscar ventana: {e}", 'status': 'Error'})
        bot_running = False
        return

    # Cargar ROIs desde settings.json y hacerlas relativas a la ventana
    with open("configs/settings.json", 'r') as f:
        settings = json.load(f)
    
    rois = {
        name: RegionOfInterest(
            left=game_window.left + roi['left'],
            top=game_window.top + roi['top'],
            width=roi['width'],
            height=roi['height']
        ) for name, roi in settings['vision']['rois'].items()
    }

    # Inicializar el resto de módulos
    vision = VisionSystem(rois, monitor_index=0) # Asumimos monitor 0 ahora que tenemos la ventana
    brain = DecisionOrchestrator(initial_bankroll=1000) # El bankroll real se leerá
    fsm = GameFSM()

    socketio.emit('status_update', {'log': 'Bot iniciado y escaneando pantalla...', 'status': 'Escaneando'})
    
    # --- Bucle Principal del Bot ---
    while bot_running:
        for event in vision.run():
            if not bot_running: break
            
            # 1. Registrar y actualizar UI con lo que ve M1
            logger.log(event)
            socketio.emit('status_update', {'log': f"EVENTO M1: {event.event_type} | Data: {event.data}"})
            
            # 2. M2 procesa el evento
            brain.counter.process_card(event) # Simplificación, se necesita más lógica
            fsm.process_event(event)
            
            # Actualizar TC en la UI
            tc_snapshot = brain.counter.get_snapshot()
            socketio.emit('status_update', {'tc': tc_snapshot['tc_current']})
            
            # 3. M3 decide si la FSM está en estado de acción
            if fsm.current_phase == "my_action":
                socketio.emit('status_update', {'status': 'Decidiendo jugada...'})
                # Lógica de decisión
                # action_request = brain.decide_play(...)
                # logger.log(action_request)
                
                # 4. M4 ejecuta la acción
                # confirmation = actuator.execute_action(action_request)
                # logger.log(confirmation)
                # socketio.emit('status_update', {'status': 'Acción ejecutada', 'last_action': confirmation['reason']})
            
            time.sleep(0.1)
        if not bot_running: break

    print("🤖 Hilo del Bot detenido.")
    socketio.emit('status_update', {'log': 'Bot detenido por el usuario.', 'status': 'Detenido'})

# --- Rutas de la API de Control ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_bot():
    global bot_thread, bot_running
    if not bot_running:
        bot_running = True
        config = request.json
        bot_thread = threading.Thread(target=bot_worker, args=(config,))
        bot_thread.start()
    return {"status": "Bot iniciado"}

@app.route('/stop', methods=['POST'])
def stop_bot():
    global bot_running
    bot_running = False
    return {"status": "Deteniendo bot..."}

if __name__ == '__main__':
    print("🚀 Iniciando Panel de Control en http://127.0.0.1:5000")
    socketio.run(app, host='127.0.0.1', port=5000)
