"""Aplicación Flask que coordina el flujo en vivo del bot de blackjack."""

from __future__ import annotations

import json
import threading
import time
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
from m4_actuacion.actuator import Actuator
from m5_metricas.logger import EventLogger
from utils.contratos import Card, Event, EventType, GamePhase
from bankroll_reader import BankrollTracker

# --- Configuración de la WebApp ---
app = Flask(__name__, template_folder="frontend")
socketio = SocketIO(app, async_mode="eventlet")
bot_thread: Optional[threading.Thread] = None
bot_running = False


class BotOrchestrator:
    """Orquestador principal que coordina todos los módulos del bot."""

    def __init__(self, config: Optional[Dict] = None) -> None:
        self.config = config or {}
        self.logger = EventLogger()
        self.current_round_id: Optional[str] = None
        self.last_bet_amount: float = 0.0

        self.game_window = None
        self.rois: Dict[str, RegionOfInterest] = {}
        self.vision: Optional[VisionSystem] = None
        self.counter: Optional[CardCounter] = None
        self.fsm: Optional[GameFSM] = None
        self.game_state: Optional[GameState] = None
        self.decision_maker: Optional[DecisionOrchestrator] = None
        self.actuator: Optional[Actuator] = None
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
        self._process_m2_event(event)
        self._update_ui_from_event(event)

        if self._check_decision_needed(event):
            self._process_m3_decision()

        self._update_bankroll_if_needed(event)

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

            confirmation = self.actuator.execute_action(action_request)
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

            confirmation = self.actuator.execute_action(action_request)
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
