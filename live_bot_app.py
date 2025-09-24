"""Aplicación Flask que coordina el flujo en vivo del bot de blackjack."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
import pyautogui
from flask import Flask, render_template, request
from flask_socketio import SocketIO

# Módulos propios
from m1_ingesta.vision_system import VisionSystem, RegionOfInterest
from m2_cerebro.contador import CardCounter
from m2_cerebro.estado_juego import GameState
from m2_cerebro.fsm import GameFSM
from m3_decision.orquestador import DecisionOrchestrator
from m4_actuacion.actuator import Actuator, SafetyWrapper
from m5_metricas.logger import EventLogger
from m5_metricas.health_monitor import HealthMonitor
from utils.contratos import Card, Event, EventType, GamePhase
from bankroll_reader import BankrollTracker

# --- Configuración de la WebApp ---
app = Flask(__name__, template_folder="frontend")
socketio = SocketIO(app, async_mode="eventlet")
bot_thread: Optional[threading.Thread] = None
bot_running = False


class GameSynchronizer:
    """Monitorea actividad del juego para detectar desincronizaciones."""

    def __init__(self, max_idle_time: float = 60.0) -> None:
        self.max_idle_time = max_idle_time
        self.last_game_activity = time.time()

    def update_activity(self) -> None:
        self.last_game_activity = time.time()

    def check_sync(self) -> bool:
        return time.time() - self.last_game_activity <= self.max_idle_time

    def reset(self) -> None:
        self.last_game_activity = time.time()


class BotOrchestrator:
    """Orquestador principal que coordina todos los módulos del bot."""

    def __init__(self, config: Optional[Dict] = None) -> None:
        self.config = config or {}
        self.logger = EventLogger()
        self.current_round_id: Optional[str] = None
        self.last_bet_amount: float = 0.0

        self.emergency_settings = self._load_emergency_settings()
        safety_cfg = self.emergency_settings.get("safety", {})
        self.safety_checks = {
            "last_successful_action": time.time(),
            "action_timeout": safety_cfg.get("action_timeout_seconds", 30),
            "emergency_stops": 0,
            "max_emergency_stops": safety_cfg.get("max_emergency_stops", 3),
        }
        monitoring_cfg = self.emergency_settings.get("monitoring", {})

        self.health_monitor = HealthMonitor()
        self._last_health_report = time.time()
        self.synchronizer = GameSynchronizer(
            max_idle_time=monitoring_cfg.get("max_idle_time", 60)
        )

        self.game_window = None
        self.rois: Dict[str, RegionOfInterest] = {}
        self.vision: Optional[VisionSystem] = None
        self.counter: Optional[CardCounter] = None
        self.fsm: Optional[GameFSM] = None
        self.game_state: Optional[GameState] = None
        self.decision_maker: Optional[DecisionOrchestrator] = None
        self.actuator: Optional[Actuator] = None
        self.safety_wrapper: Optional[SafetyWrapper] = None
        self.bankroll_tracker: Optional[BankrollTracker] = None

        self._initialize_modules()

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------
    def _initialize_modules(self) -> None:
        game_window = self._find_game_window()
        if not game_window:
            raise RuntimeError("No se encontró la ventana del juego")

        self.game_window = game_window
        self.rois = self._load_rois(game_window)

        monitor_index = self.config.get("monitor_index", 0)
        poll_interval = self.config.get("poll_interval", 0.5)
        self.vision = VisionSystem(
            self.rois,
            monitor_index=monitor_index,
            poll_interval=poll_interval,
        )

        counting_system = self.config.get("system", "hilo")
        self.counter = CardCounter(system=counting_system)
        self.fsm = GameFSM()
        self.game_state = GameState()

        initial_bankroll = float(self.config.get("initial_bankroll", 1000))
        self.decision_maker = DecisionOrchestrator(initial_bankroll=initial_bankroll)
        self.actuator = Actuator()
        self.safety_wrapper = SafetyWrapper(self.actuator)
        max_failures = self.emergency_settings.get("safety", {}).get(
            "max_consecutive_failures", 3
        )
        self.safety_wrapper.max_failures = max_failures
        self.bankroll_tracker = BankrollTracker(initial_bankroll=initial_bankroll)

        socketio.emit(
            "status_update",
            {"log": "Todos los módulos inicializados correctamente", "status": "Inicializado"},
        )

    def _find_game_window(self):
        """Encuentra y activa la ventana del juego en el sistema operativo."""
        try:
            windows = pyautogui.getWindowsWithTitle("Caliente.mx")
            if not windows:
                windows = pyautogui.getWindowsWithTitle("Chrome")

            if not windows:
                return None

            game_window = windows[0]
            game_window.activate()
            time.sleep(1)
            return game_window
        except Exception as exc:  # pragma: no cover - depende del SO
            print(f"Error finding game window: {exc}")
            return None

    def _load_rois(self, game_window) -> Dict[str, RegionOfInterest]:
        """Carga las ROIs desde configuración y las ajusta a la ventana detectada."""
        with open("configs/settings.json", "r", encoding="utf-8") as handler:
            settings = json.load(handler)

        rois: Dict[str, RegionOfInterest] = {}
        for name, roi_config in settings.get("vision", {}).get("rois", {}).items():
            rois[name] = RegionOfInterest(
                left=game_window.left + roi_config["left"],
                top=game_window.top + roi_config["top"],
                width=roi_config["width"],
                height=roi_config["height"],
            )
        return rois

    def _load_emergency_settings(self) -> Dict[str, Dict]:
        """Carga configuración de seguridad con valores por defecto."""
        default_settings = {
            "safety": {
                "max_consecutive_failures": 3,
                "action_timeout_seconds": 30,
                "max_emergency_stops": 3,
                "health_check_interval": 60,
                "auto_recalibration_enabled": True,
            },
            "monitoring": {
                "min_success_rate": 0.7,
                "min_ocr_confidence": 0.6,
                "max_phase_errors": 5,
                "bankroll_read_timeout": 10,
                "max_idle_time": 60,
            },
            "recovery": {
                "pause_on_ui_change": True,
                "reset_on_desync": True,
                "notification_webhook": None,
            },
        }

        config_path = Path("configs/emergency_settings.json")
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as handler:
                    loaded = json.load(handler)
            except Exception:
                loaded = {}
        else:
            loaded = {}

        merged = json.loads(json.dumps(default_settings))  # copia profunda
        for section, values in loaded.items():
            if not isinstance(values, dict):
                continue
            merged.setdefault(section, {})
            for key, value in values.items():
                merged[section][key] = value

        return merged

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def run(self) -> None:
        if not self.vision:
            raise RuntimeError("VisionSystem no inicializado")

        socketio.emit(
            "status_update",
            {"log": "Bot iniciado - comenzando bucle principal", "status": "Ejecutando"},
        )

        try:
            for event in self.vision.run():
                if not bot_running:
                    self.vision.stop()
                    break

                self._process_event(event)
                time.sleep(self.config.get("loop_sleep", 0.1))
        except Exception as exc:
            socketio.emit(
                "status_update",
                {"log": f"Error en bucle principal: {exc}", "status": "Error"},
            )
            raise
        finally:
            socketio.emit(
                "status_update",
                {"log": "Bot detenido", "status": "Detenido"},
            )

    # ------------------------------------------------------------------
    # Procesamiento de eventos
    # ------------------------------------------------------------------
    def _process_event(self, event: Event) -> None:
        self.logger.log(event)
        if self.synchronizer:
            self.synchronizer.update_activity()

        self._update_health_from_event(event)
        self._process_m2_event(event)
        self._update_ui_from_event(event)

        if self._check_decision_needed(event):
            self._process_m3_decision()

        self._update_bankroll_if_needed(event)
        self._maybe_emit_health_report()

    def _process_m2_event(self, event: Event) -> None:
        if not (self.counter and self.fsm and self.game_state):
            return

        new_phase = self.fsm.process_event(event)
        if new_phase:
            self.game_state.set_phase(new_phase)
            socketio.emit(
                "status_update",
                {"log": f"Fase cambiada: {new_phase.value}", "status": f"Fase: {new_phase.value}"},
            )

        if event.event_type in (EventType.CARD_DEALT, EventType.CARD_DEALT_SHARED):
            cards_data = event.data or {}
            raw_cards: List[str] = []
            if isinstance(cards_data.get("cards"), list):
                raw_cards = cards_data["cards"]
            elif cards_data.get("card"):
                raw_cards = [cards_data["card"]]

            target = (cards_data.get("who") or cards_data.get("target") or "").lower()
            for card_str in raw_cards:
                card = self._parse_card(card_str)
                if not card:
                    continue

                self.counter.process_card(card)

                if "dealer" in target:
                    is_hole = "hole" in target
                    self.game_state.add_dealer_card(card, is_hole=is_hole)
                elif target in ("player_cards", "shared") or "player" in target:
                    self.game_state.add_shared_card(card)
                else:
                    self.game_state.add_others_card(card)

        if event.event_type == EventType.ROUND_START:
            self.current_round_id = event.round_id
            self.game_state.start_round(event.round_id)

        elif event.event_type == EventType.ROUND_END:
            result_data = event.data or {}
            result = result_data.get("result")
            amount = float(result_data.get("amount", 0))
            if result:
                self.game_state.record_result(result)

            if self.decision_maker:
                if result == "win":
                    self.decision_maker.update_result(True, amount)
                elif result == "loss":
                    self.decision_maker.update_result(False, amount)

            self.current_round_id = None

    def _update_health_from_event(self, event: Event) -> None:
        if not self.health_monitor:
            return

        data = event.data or {}
        if event.event_type == EventType.STATE_TEXT:
            confidence = data.get("confidence")
            if confidence is not None:
                try:
                    self.health_monitor.update_ocr_confidence(float(confidence))
                except (TypeError, ValueError):
                    pass

    def _maybe_emit_health_report(self) -> None:
        if not self.health_monitor:
            return

        interval = self.emergency_settings.get("safety", {}).get(
            "health_check_interval", 60
        )
        if time.time() - self._last_health_report < interval:
            return

        report = self.health_monitor.generate_health_report()
        socketio.emit("health_update", report)
        self._last_health_report = time.time()

    def _parse_card(self, card_str: Optional[str]) -> Optional[Card]:
        if not card_str or len(card_str) < 2:
            return None

        rank = card_str[:-1]
        suit = card_str[-1]
        if rank == "10":
            rank = "T"
        return Card(rank=rank, suit=suit)

    def _update_ui_from_event(self, event: Event) -> None:
        event_log = f"M1: {event.event_type.value}"
        if event.data:
            if event.event_type == EventType.CARD_DEALT_SHARED:
                cards = event.data.get("cards", [])
                if cards:
                    event_log += f" | Cartas: {', '.join(cards)}"
            elif event.event_type == EventType.STATE_TEXT:
                state_text = event.data.get("text") or event.data.get("phase", "")
                if state_text:
                    event_log += f" | Estado: {state_text}"

        socketio.emit("status_update", {"log": event_log})

        if self.counter:
            tc_snapshot = self.counter.get_snapshot()
            socketio.emit("status_update", {"tc": tc_snapshot.get("tc_current", 0)})

        if self.game_state and self.fsm:
            game_status = self.game_state.get_state()
            fsm_status = self.fsm.get_state()
            socketio.emit(
                "status_update",
                {
                    "phase": fsm_status.get("current_phase"),
                    "hand_value": game_status.get("my_hand_value", 0),
                    "dealer_up": game_status.get("dealer_up_value", 0),
                },
            )

    def _check_decision_needed(self, event: Event) -> bool:
        if not self.fsm:
            return False

        current_phase = self.fsm.current_phase
        if event.event_type != EventType.STATE_TEXT:
            return False

        state_data = event.data or {}
        phase_text = (state_data.get("phase") or state_data.get("text") or "").lower()

        if current_phase == GamePhase.MY_ACTION and any(
            keyword in phase_text for keyword in ("player_action", "your_turn", "realiza", "my_action")
        ):
            return True

        if current_phase == GamePhase.BETS_OPEN and any(
            keyword in phase_text for keyword in ("place", "bet", "apuesta", "bets_open")
        ):
            return True

        return False

    def _process_m3_decision(self) -> None:
        if not (self.fsm and self.decision_maker and self.game_state and self.counter):
            return

        current_phase = self.fsm.current_phase
        if current_phase == GamePhase.MY_ACTION:
            self._make_play_decision()
        elif current_phase == GamePhase.BETS_OPEN:
            self._make_bet_decision()

    def _make_play_decision(self) -> None:
        if not (self.decision_maker and self.game_state and self.counter):
            return

        try:
            game_state = self.game_state.get_state()
            hand_value = game_state.get("my_hand_value", 0)
            is_soft = game_state.get("my_hand_soft", False)
            dealer_up = game_state.get("dealer_up_value", 0)

            if hand_value == 0 or dealer_up == 0:
                socketio.emit(
                    "status_update",
                    {"log": "No hay suficiente información para decidir jugada", "status": "Esperando información"},
                )
                return

            tc_snapshot = self.counter.get_snapshot()
            self.decision_maker.process_count_update(tc_snapshot)

            decision = self.decision_maker.decide_play(
                hand_value=hand_value,
                is_soft=is_soft,
                dealer_up=dealer_up,
                can_double=True,
                can_split=False,
            )

            decision_event = Event.create(
                EventType.PLAY_ADVICE,
                round_id=self.current_round_id,
                action=decision["action"].value,
                reason=decision["reason"],
                tc_used=decision["tc_used"],
                confidence=decision["confidence"],
            )
            self.logger.log(decision_event)

            socketio.emit(
                "status_update",
                {
                    "log": f"M3 DECISIÓN: {decision['action'].value} | {decision['reason']}",
                    "status": "Decidiendo...",
                    "last_decision": decision["action"].value,
                },
            )

            self._execute_play_action(decision)
        except Exception as exc:
            socketio.emit(
                "status_update",
                {"log": f"Error en decisión de jugada: {exc}", "status": "Error"},
            )

    def _make_bet_decision(self) -> None:
        if not (self.decision_maker and self.counter):
            return

        try:
            tc_snapshot = self.counter.get_snapshot()
            tc_for_bet = tc_snapshot.get("tc_post", tc_snapshot.get("tc_current", 0))

            bet_decision = self.decision_maker.decide_bet(tc_post=tc_for_bet)

            bet_event = Event.create(
                EventType.BET_ADVICE_NEXT_ROUND,
                round_id=self.current_round_id,
                units=bet_decision.get("units"),
                amount=bet_decision.get("amount"),
                rationale=bet_decision.get("rationale"),
                should_sit=bet_decision.get("should_sit"),
            )
            self.logger.log(bet_event)

            socketio.emit(
                "status_update",
                {
                    "log": f"M3 APUESTA: ${bet_decision['amount']} | {bet_decision['rationale']}",
                    "status": "Apostando...",
                },
            )

            if bet_decision.get("should_sit"):
                socketio.emit(
                    "status_update",
                    {"log": "Saltando ronda por condiciones adversas", "status": "Sentado"},
                )
                return

            self.last_bet_amount = float(bet_decision.get("amount", 0))
            self._execute_bet_action(bet_decision)
        except Exception as exc:
            socketio.emit(
                "status_update",
                {"log": f"Error en decisión de apuesta: {exc}", "status": "Error"},
            )

    def safety_check(self) -> bool:
        """Verificaciones de seguridad antes de ejecutar acciones."""
        current_time = time.time()
        timeout = self.safety_checks.get("action_timeout")
        if timeout and current_time - self.safety_checks["last_successful_action"] > timeout:
            self.emergency_pause("Action timeout - possible UI freeze")
            return False

        try:
            windows = pyautogui.getWindowsWithTitle("Caliente.mx")
            if not windows:
                windows = pyautogui.getWindowsWithTitle("Caliente")
            if not windows:
                self.emergency_pause("Game window not found")
                return False
        except Exception:
            self.emergency_pause("Unable to verify game window")
            return False

        if self.safety_checks["emergency_stops"] >= self.safety_checks["max_emergency_stops"]:
            return False

        if self.synchronizer and not self.synchronizer.check_sync():
            self.emergency_pause("Game heartbeat lost")
            if self.emergency_settings.get("recovery", {}).get("reset_on_desync", True):
                self.synchronizer.reset()
            return False

        return True

    def emergency_pause(self, reason: str) -> None:
        """Pausa de emergencia del bot y notifica a la interfaz."""
        global bot_running
        bot_running = False

        self.safety_checks["emergency_stops"] += 1

        socketio.emit(
            "status_update",
            {"log": f"🚨 PARADA DE EMERGENCIA: {reason}", "status": "EMERGENCIA"},
        )

        emergency_event = {
            "timestamp": time.time(),
            "event_type": "EMERGENCY_STOP",
            "reason": reason,
            "safety_stats": self.safety_checks.copy(),
        }
        self.logger.log(emergency_event)

    def verify_game_state(self) -> bool:
        if not (self.fsm and self.game_state):
            return False

        try:
            windows = pyautogui.getWindowsWithTitle("Caliente.mx")
            if not windows:
                windows = pyautogui.getWindowsWithTitle("Caliente")
            return bool(windows)
        except Exception:
            return False

    def verify_action_effect(self, action_request: Dict, result: Dict) -> bool:
        if not result.get("ok"):
            return False
        if not self.actuator:
            return False

        action_type = action_request.get("type")
        payload = action_request.get("payload", {})
        try:
            return self.actuator._validate_action_effect(  # type: ignore[attr-defined]
                action_type,
                payload,
                getattr(self.actuator, "_last_action_snapshot", None),
            )
        except Exception:
            return True

    def execute_with_verification(self, action_request: Dict) -> Dict:
        if not self.safety_check():
            return {"ok": False, "error": "Safety check failed"}

        if not self.verify_game_state():
            self.emergency_pause("Game state verification failed")
            return {"ok": False, "error": "Game state verification failed"}

        if not self.safety_wrapper:
            return {"ok": False, "error": "Safety wrapper not initialized"}

        result = self.safety_wrapper.safe_execute(action_request)

        if (
            not result.get("ok")
            and result.get("error") == "Safety limit reached - stopping bot"
        ):
            self.emergency_pause(result.get("error", "Safety limit reached"))
            return result

        if result.get("ok") and not self.verify_action_effect(action_request, result):
            result = result.copy()
            result["ok"] = False
            result["error"] = "Action effect verification failed"
            self.emergency_pause("Action effect verification failed")

        if result.get("ok"):
            self.safety_checks["last_successful_action"] = time.time()
        else:
            if self.emergency_settings.get("safety", {}).get("auto_recalibration_enabled", True):
                if self.actuator:
                    self.actuator.trigger_recalibration()

        if self.health_monitor:
            self.health_monitor.update_action_result(result.get("ok", False))

        self._maybe_emit_health_report()
        return result

    def _execute_play_action(self, decision: Dict) -> None:
        if not self.actuator:
            return

        try:
            action_request = {
                "type": "PLAY",
                "payload": {
                    "move": decision["action"].value,
                    "confidence": decision["confidence"],
                },
            }

            confirmation = self.execute_with_verification(action_request)
            self.logger.log(confirmation)

            if confirmation.get("ok"):
                socketio.emit(
                    "status_update",
                    {
                        "log": f"M4 EJECUTADO: {decision['action'].value}",
                        "status": "Acción ejecutada",
                    },
                )
                if self.game_state:
                    self.game_state.last_decision = decision["action"].value
            else:
                error = confirmation.get("error", "Error desconocido")
                socketio.emit(
                    "status_update",
                    {"log": f"M4 ERROR: {error}", "status": "Error de ejecución"},
                )
        except Exception as exc:
            socketio.emit(
                "status_update",
                {"log": f"Error ejecutando acción: {exc}", "status": "Error"},
            )

    def _execute_bet_action(self, bet_decision: Dict) -> None:
        if not self.actuator:
            return

        try:
            amount = float(bet_decision.get("amount", 0))
            chip_action = self._select_bet_chip(amount)

            action_request = {
                "type": "BET",
                "payload": {
                    "amount": amount,
                    "units": bet_decision.get("units"),
                    "chip_type": chip_action,
                },
            }

            confirmation = self.execute_with_verification(action_request)
            self.logger.log(confirmation)

            if confirmation.get("ok"):
                socketio.emit(
                    "status_update",
                    {"log": f"M4 APUESTA: ${amount}", "status": "Apuesta realizada"},
                )
            else:
                error = confirmation.get("error", "Error desconocido")
                socketio.emit(
                    "status_update",
                    {"log": f"M4 ERROR APUESTA: {error}", "status": "Error de apuesta"},
                )
        except Exception as exc:
            socketio.emit(
                "status_update",
                {"log": f"Error ejecutando apuesta: {exc}", "status": "Error"},
            )

    def _select_bet_chip(self, amount: float) -> Optional[str]:
        """Selecciona la acción de ficha más adecuada basada en el mapa del actuador."""
        if not self.actuator:
            return None

        chip_entries = []
        for key in self.actuator.action_map.keys():
            if not key.startswith("BET_"):
                continue
            try:
                value = int("".join(filter(str.isdigit, key)))
            except ValueError:
                continue
            chip_entries.append((value, key))

        if not chip_entries:
            return None

        chip_entries.sort()
        selected = chip_entries[0][1]
        for value, key in chip_entries:
            if amount >= value:
                selected = key
        return selected

    def _update_bankroll_if_needed(self, event: Event) -> None:
        """Actualiza el bankroll si hay ROI disponible y el evento lo amerita."""
        if not (self.bankroll_tracker and self.rois):
            return

        if event.event_type not in (EventType.STATE_TEXT, EventType.ROUND_END):
            return

        bankroll_roi = self.rois.get("bankroll_area")
        if not bankroll_roi:
            return

        try:
            screenshot = pyautogui.screenshot()
            screenshot_np = np.array(screenshot)  # RGB
            bankroll_image = bankroll_roi.extract(screenshot_np)
            if bankroll_image.size == 0:
                return

            # BankrollReader maneja conversión a gris internamente; RGB/BGR no afecta a la conversión a gris
            current_bankroll, updated = self.bankroll_tracker.update_from_roi(
                bankroll_image, self.last_bet_amount
            )

            if updated and self.decision_maker:
                self.decision_maker.risk_manager.update_bankroll(current_bankroll)

                initial = self.bankroll_tracker.history[0]
                pnl = current_bankroll - initial
                socketio.emit(
                    "status_update",
                    {"bankroll": current_bankroll, "pnl": pnl},
                )
        except Exception as exc:
            print(f"Error updating bankroll: {exc}")
            if self.health_monitor:
                self.health_monitor.increment_bankroll_failure()


# --- El Motor del Bot ---
def bot_worker(config: Optional[Dict]) -> None:
    global bot_running
    print("🤖 Hilo del Bot iniciado con la configuración:", config)

    try:
        orchestrator = BotOrchestrator(config)
        orchestrator.run()
    except Exception as exc:
        socketio.emit(
            "status_update",
            {"log": f"ERROR CRÍTICO: {exc}", "status": "Error crítico"},
        )
        print(f"Critical error in bot_worker: {exc}")
    finally:
        bot_running = False


# --- Rutas de la API de Control ---
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start_bot():
    global bot_thread, bot_running
    if not bot_running:
        bot_running = True
        config = request.get_json(silent=True) or {}
        config.setdefault("initial_bankroll", 1000)

        bot_thread = threading.Thread(target=bot_worker, args=(config,), daemon=True)
        bot_thread.start()
    return {"status": "Bot iniciado"}


@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return {"status": "Deteniendo bot..."}


@app.route("/calibrate", methods=["POST"])
def run_calibration():
    """Endpoint para ejecutar calibración desde la web."""
    try:
        from calibration_tool import CalibrationTool  # type: ignore

        calibrator = CalibrationTool()
        success = calibrator.run_calibration()

        if success:
            return {"status": "Calibración exitosa"}
        return {"status": "Calibración fallida", "error": "Ver logs del sistema"}
    except Exception as exc:
        return {"status": "Error", "error": str(exc)}


if __name__ == "__main__":
    print("🚀 Iniciando Panel de Control en http://127.0.0.1:5000")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False)
