"""Integración completa del sistema mejorado de Blackjack Bot.

Este archivo implementa las mejoras del plan de evolución y sirve como
referencia para la versión avanzada del orquestador en vivo.

Implementa las 3 fases:
1. Calibración Inteligente y Permanente
2. Panel de Control (Cockpit)
3. Control Total y Robustez
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from flask import Flask, render_template, request
from flask_socketio import SocketIO

from calibration_tool_improved import ImprovedCalibrationTool
from m1_ingesta.enhanced_vision_system import AllBetsBlackjackVision, RegionOfInterest
from m2_cerebro.contador import CardCounter
from m2_cerebro.estado_juego import GameState
from m2_cerebro.fsm import GameFSM
from m3_decision.orquestador import DecisionOrchestrator
from m4_actuacion.hybrid_actuator_system import (
    GameWindowDetector,
    HybridActuator,
    SafetyWrapper,
)
from m5_metricas.health_monitor import HealthMonitor
from m5_metricas.logger import EventLogger
from utils.contratos import Card, Event, EventType, GamePhase
from bankroll_reader import BankrollTracker

# Configuración de la WebApp
app = Flask(__name__, template_folder="frontend")
socketio = SocketIO(app, async_mode="eventlet")
bot_thread: Optional[threading.Thread] = None
bot_running = False

current_orchestrator: Optional["EnhancedBotOrchestrator"] = None
orchestrator_lock = threading.Lock()


class EnhancedBotOrchestrator:
    """Orquestador mejorado con todos los sistemas optimizados."""

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

        self.health_monitor = HealthMonitor()
        self._last_health_report = time.time()

        self.game_window_detector = GameWindowDetector()
        self.window_info: Optional[Dict] = None
        self.rois: Dict[str, RegionOfInterest] = {}

        self.vision: Optional[AllBetsBlackjackVision] = None
        self.counter: Optional[CardCounter] = None
        self.fsm: Optional[GameFSM] = None
        self.game_state: Optional[GameState] = None
        self.decision_maker: Optional[DecisionOrchestrator] = None
        self.actuator: Optional[HybridActuator] = None
        self.safety_wrapper: Optional[SafetyWrapper] = None
        self.bankroll_tracker: Optional[BankrollTracker] = None

        self.session_stats = {
            "start_time": time.time(),
            "rounds_processed": 0,
            "cards_detected": 0,
            "actions_executed": 0,
            "emergency_stops": 0,
        }

        self._last_thinking: Dict[str, Any] = {}
        self._last_financial_metrics: Dict[str, float] = {}

        self._initialize_enhanced_modules()

    def _emit_status_update(self, payload: Dict[str, Any], thinking: Optional[Dict[str, Any]] = None) -> None:
        """Emite actualizaciones enriquecidas conservando el último contexto."""

        message = dict(payload)
        if thinking is not None:
            context = dict(thinking)
            context.setdefault("timestamp", time.time())
            self._last_thinking = context
            message["thinking"] = context

        socketio.emit("status_update", message)

    def _initialize_enhanced_modules(self) -> None:
        """Inicializa todos los módulos con las mejoras implementadas."""

        socketio.emit(
            "status_update",
            {"log": "Iniciando sistema mejorado...", "status": "Inicializando"},
        )

        game_window = self._find_and_setup_game_window()
        if not game_window:
            raise RuntimeError("No se encontró la ventana de All Bets Blackjack")

        self.window_info = {
            "title": getattr(game_window, "title", "Unknown"),
            "width": getattr(game_window, "width", 0),
            "height": getattr(game_window, "height", 0),
            "left": getattr(game_window, "left", 0),
            "top": getattr(game_window, "top", 0),
        }

        socketio.emit(
            "status_update",
            {
                "log": f"Ventana detectada: {self.window_info['title']}",
                "status": "Ventana encontrada",
            },
        )

        self.rois = self._setup_hybrid_rois(game_window)

        monitor_index = self.config.get("monitor_index", 1)
        poll_interval = self.config.get("poll_interval", 0.4)
        self.vision = AllBetsBlackjackVision(
            self.rois,
            monitor_index=monitor_index,
            poll_interval=poll_interval,
        )
        self.vision.configure_for_all_bets_mode()

        socketio.emit(
            "status_update",
            {
                "log": "Sistema de visión optimizado para All Bets Blackjack",
                "status": "Visión configurada",
            },
        )

        counting_system = self.config.get("system", "hilo")
        self.counter = CardCounter(system=counting_system)
        self.fsm = GameFSM()
        self.game_state = GameState()

        initial_bankroll = float(self.config.get("initial_bankroll", 1000))
        self.decision_maker = DecisionOrchestrator(initial_bankroll=initial_bankroll)

        self.actuator = HybridActuator()
        self.safety_wrapper = SafetyWrapper(self.actuator)
        max_failures = self.emergency_settings.get("safety", {}).get(
            "max_consecutive_failures", 3
        )
        self.safety_wrapper.max_failures = max_failures

        self.bankroll_tracker = BankrollTracker(initial_bankroll=initial_bankroll)

        socketio.emit(
            "status_update",
            {"log": "Todos los módulos mejorados inicializados correctamente", "status": "Sistema listo"},
        )

    def _find_and_setup_game_window(self) -> Optional[object]:
        """Encuentra y configura la ventana del juego con sistema mejorado."""

        print("🔍 Buscando ventana de All Bets Blackjack...")
        game_window = self.game_window_detector.get_game_window()

        if game_window:
            print(f"✅ Ventana encontrada: {getattr(game_window, 'title', 'Unknown')}")
            try:
                game_window.activate()
                time.sleep(1.5)
                print("✅ Ventana activada correctamente")
            except Exception as exc:  # pragma: no cover - depende del SO
                print(f"⚠️ No se pudo activar ventana: {exc}")
            return game_window

        print("❌ No se encontró ventana de All Bets Blackjack")
        return None

    def _setup_hybrid_rois(self, game_window) -> Dict[str, RegionOfInterest]:
        """Configura ROIs usando sistema híbrido."""

        rois: Dict[str, RegionOfInterest] = {}
        settings_path = Path("configs/settings.json")
        if settings_path.exists():
            try:
                with settings_path.open("r", encoding="utf-8") as handler:
                    settings = json.load(handler)
                vision_rois = settings.get("vision", {}).get("rois", {})
                for name, roi_config in vision_rois.items():
                    rois[name] = RegionOfInterest(
                        left=roi_config["left"],
                        top=roi_config["top"],
                        width=roi_config["width"],
                        height=roi_config["height"],
                    )
                print(f"✅ Cargadas {len(rois)} ROIs desde configuración")
            except Exception as exc:  # pragma: no cover - lectura opcional
                print(f"⚠️ Error cargando ROIs: {exc}")

        if not rois:
            rois = self._generate_default_rois(game_window)
            print(f"✅ Generadas {len(rois)} ROIs por defecto")

        return rois

    def _generate_default_rois(self, game_window) -> Dict[str, RegionOfInterest]:
        """Genera ROIs por defecto basadas en coordenadas relativas."""

        window_width = getattr(game_window, "width", 1200)
        window_height = getattr(game_window, "height", 800)
        window_left = getattr(game_window, "left", 0)
        window_top = getattr(game_window, "top", 0)

        relative_rois = {
            "dealer_cards": {"rel_coords": (0.50, 0.20), "size": (200, 120)},
            "player_cards": {"rel_coords": (0.50, 0.65), "size": (250, 150)},
            "others_cards_area": {"rel_coords": (0.50, 0.45), "size": (1000, 200)},
            "game_status": {"rel_coords": (0.50, 0.35), "size": (400, 80)},
            "bankroll_area": {"rel_coords": (0.85, 0.05), "size": (150, 30)},
        }

        rois: Dict[str, RegionOfInterest] = {}
        for name, config in relative_rois.items():
            rel_x, rel_y = config["rel_coords"]
            width, height = config["size"]
            center_x = int(window_left + window_width * rel_x)
            center_y = int(window_top + window_height * rel_y)
            left = center_x - width // 2
            top = center_y - height // 2
            rois[name] = RegionOfInterest(left=left, top=top, width=width, height=height)

        return rois

    def _load_emergency_settings(self) -> Dict[str, Dict]:
        """Carga configuración de emergencia."""

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
                with config_path.open("r", encoding="utf-8") as handler:
                    loaded = json.load(handler)
                merged = json.loads(json.dumps(default_settings))
                for section, values in loaded.items():
                    if isinstance(values, dict):
                        merged.setdefault(section, {}).update(values)
                return merged
            except Exception:  # pragma: no cover - depende de archivo externo
                pass

        return default_settings

    def run(self) -> None:
        """Ejecuta el bucle principal mejorado."""

        if not self.vision:
            raise RuntimeError("Sistema de visión no inicializado")

        socketio.emit(
            "status_update",
            {"log": "Bot iniciado - comenzando bucle principal mejorado", "status": "Ejecutando"},
        )

        try:
            for event in self.vision.run():
                if not bot_running:
                    self.vision.stop()
                    break

                self._process_event_enhanced(event)
                time.sleep(0.05)
        except Exception as exc:  # pragma: no cover - runtime loop
            socketio.emit(
                "status_update",
                {"log": f"Error en bucle principal: {exc}", "status": "Error"},
            )
            raise
        finally:
            socketio.emit(
                "status_update", {"log": "Bot detenido", "status": "Detenido"}
            )

    def _process_event_enhanced(self, event: Event) -> None:
        """Procesamiento mejorado de eventos."""

        self.logger.log(event)
        self.session_stats["rounds_processed"] += 1
        self._update_health_from_event(event)
        self._process_m2_event_enhanced(event)
        self._update_ui_from_event_enhanced(event)

        if self._check_decision_needed_enhanced(event):
            self._process_m3_decision_enhanced()

        self._update_bankroll_enhanced(event)
        self._maybe_emit_health_report()

    def _process_m2_event_enhanced(self, event: Event) -> None:
        """Procesamiento mejorado en M2 con mejor manejo de cartas compartidas."""

        if not (self.counter and self.fsm and self.game_state):
            return

        new_phase = self.fsm.process_event(event)
        if new_phase:
            self.game_state.set_phase(new_phase)
            socketio.emit(
                "status_update",
                {"log": f"Fase: {new_phase.value}", "phase": new_phase.value},
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
                card = self._parse_card_enhanced(card_str)
                if not card:
                    continue

                self.counter.process_card(card)
                self.session_stats["cards_detected"] += 1

                if "dealer" in target:
                    is_hole = "hole" in target
                    self.game_state.add_dealer_card(card, is_hole=is_hole)
                elif target in ("player_shared", "shared") or "player" in target:
                    self.game_state.add_shared_card(card)
                else:
                    self.game_state.add_others_card(card)

        if event.event_type == EventType.ROUND_START:
            self.current_round_id = event.round_id
            self.game_state.start_round(event.round_id)
            if self.vision:
                self.vision.update_round_id(event.round_id)

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

    def _parse_card_enhanced(self, card_str: Optional[str]) -> Optional[Card]:
        """Parsing mejorado de cartas con validación."""

        if not card_str or len(card_str) < 2:
            return None

        try:
            card_str = card_str.strip().upper()
            if len(card_str) == 2:
                rank, suit = card_str[0], card_str[1]
            elif len(card_str) == 3 and card_str.startswith("10"):
                rank, suit = "T", card_str[2]
            else:
                return None

            valid_ranks = {"2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"}
            valid_suits = {"H", "D", "C", "S"}

            if rank in valid_ranks and suit in valid_suits:
                return Card(rank=rank, suit=suit)
        except Exception as exc:  # pragma: no cover - validación defensiva
            print(f"⚠️ Error parsing card '{card_str}': {exc}")
        return None

    def _update_ui_from_event_enhanced(self, event: Event) -> None:
        """Actualización mejorada de la interfaz."""

        event_log = f"M1: {event.event_type.value}"

        if event.data:
            if event.event_type == EventType.CARD_DEALT_SHARED:
                cards = event.data.get("cards", [])
                who = event.data.get("who", "unknown")
                if cards:
                    event_log += f" | {who}: {', '.join(cards)}"
            elif event.event_type == EventType.CARD_DEALT:
                card = event.data.get("card", "")
                who = event.data.get("who", "unknown")
                if card:
                    event_log += f" | {who}: {card}"
            elif event.event_type == EventType.STATE_TEXT:
                phase = event.data.get("phase", "")
                text = event.data.get("text", "")
                if phase:
                    event_log += f" | Fase: {phase}"
                if text:
                    event_log += f" | Texto: {text[:30]}"

        socketio.emit("status_update", {"log": event_log})

        if self.counter:
            tc_snapshot = self.counter.get_snapshot()
            socketio.emit(
                "status_update",
                {
                    "tc": tc_snapshot.get("tc_current", 0),
                    "cards_seen": tc_snapshot.get("cards_seen", 0),
                    "decks_remaining": tc_snapshot.get("decks_remaining", 0),
                },
            )

        if self.game_state and self.fsm:
            game_status = self.game_state.get_state()
            fsm_status = self.fsm.get_state()
            socketio.emit(
                "status_update",
                {
                    "phase": fsm_status.get("current_phase", "idle"),
                    "hand_value": game_status.get("my_hand_value", 0),
                    "dealer_up": game_status.get("dealer_up_value", 0),
                    "round_count": game_status.get("round_count", 0),
                },
            )

    def _check_decision_needed_enhanced(self, event: Event) -> bool:
        """Verificación mejorada de necesidad de decisión."""

        if not self.fsm or event.event_type != EventType.STATE_TEXT:
            return False

        current_phase = self.fsm.current_phase
        state_data = event.data or {}
        detected_phase = state_data.get("phase", "").lower()
        text = state_data.get("text", "").lower()

        if current_phase == GamePhase.MY_ACTION:
            action_keywords = ["your turn", "tu turno", "player action", "realiza", "decide"]
            if detected_phase == "my_action" or any(keyword in text for keyword in action_keywords):
                return True

        if current_phase == GamePhase.BETS_OPEN:
            bet_keywords = ["place", "bet", "apuesta", "betting"]
            if detected_phase == "bets_open" or any(keyword in text for keyword in bet_keywords):
                return True

        return False

    def _process_m3_decision_enhanced(self) -> None:
        """Procesamiento mejorado de decisiones M3."""

        if not (self.fsm and self.decision_maker and self.game_state and self.counter):
            return

        current_phase = self.fsm.current_phase
        if current_phase == GamePhase.MY_ACTION:
            self._make_play_decision_enhanced()
        elif current_phase == GamePhase.BETS_OPEN:
            self._make_bet_decision_enhanced()

    def _make_play_decision_enhanced(self) -> None:
        """Decisión de jugada mejorada."""

        if not (self.decision_maker and self.game_state and self.counter):
            return

        try:
            game_state = self.game_state.get_state()
            hand_value = game_state.get("my_hand_value", 0)
            is_soft = game_state.get("my_hand_soft", False)
            dealer_up = game_state.get("dealer_up_value", 0)

            tc_snapshot = self.counter.get_snapshot()

            if hand_value == 0 or dealer_up == 0:
                thinking_context = {
                    "mode": "play",
                    "state": "waiting_data",
                    "phase": self.fsm.current_phase.value if self.fsm else "unknown",
                    "hand_value": hand_value,
                    "dealer_up": dealer_up,
                    "is_soft": bool(is_soft),
                    "true_count": tc_snapshot.get("tc_current", 0.0),
                    "cards_seen": tc_snapshot.get("cards_seen"),
                    "decks_remaining": tc_snapshot.get("decks_remaining"),
                }
                self._emit_status_update(
                    {"log": "Información insuficiente para decidir jugada", "status": "Esperando datos"},
                    thinking_context,
                )
                return

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

            thinking_context = {
                "mode": "play",
                "state": "decision",
                "phase": self.fsm.current_phase.value if self.fsm else "unknown",
                "hand_value": hand_value,
                "dealer_up": dealer_up,
                "is_soft": bool(is_soft),
                "true_count": decision.get("tc_used", tc_snapshot.get("tc_current", 0.0)),
                "cards_seen": tc_snapshot.get("cards_seen"),
                "decks_remaining": tc_snapshot.get("decks_remaining"),
                "recommended_action": decision["action"].value,
                "reason": decision["reason"],
                "confidence": decision["confidence"],
                "risk_state": decision.get("risk_state"),
                "risk_message": decision.get("risk_message"),
                "risk_factor": decision.get("risk_factor"),
                "next_bet_planned": getattr(self.decision_maker, "next_bet", None),
            }

            self._emit_status_update(
                {
                    "log": f"M3 DECISIÓN: {decision['action'].value} | {decision['reason']} | TC:{decision['tc_used']:.1f}",
                    "status": "Decidiendo...",
                    "last_decision": decision["action"].value,
                },
                thinking_context,
            )

            self._execute_play_action_enhanced(decision)
        except Exception as exc:  # pragma: no cover - depende de flujo runtime
            self._emit_status_update(
                {"log": f"Error en decisión de jugada: {exc}", "status": "Error"},
                {
                    "mode": "play",
                    "state": "error",
                    "error": str(exc),
                },
            )

    def _make_bet_decision_enhanced(self) -> None:
        """Decisión de apuesta mejorada."""

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

            thinking_context = {
                "mode": "bet",
                "state": "planning",
                "phase": self.fsm.current_phase.value if self.fsm else "unknown",
                "true_count": tc_for_bet,
                "cards_seen": tc_snapshot.get("cards_seen"),
                "decks_remaining": tc_snapshot.get("decks_remaining"),
                "recommended_bet": bet_decision.get("amount"),
                "units": bet_decision.get("units"),
                "rationale": bet_decision.get("rationale"),
                "risk_state": bet_decision.get("risk_state"),
                "should_sit": bet_decision.get("should_sit"),
            }

            status_message = "Apostando..."
            log_message = (
                f"M3 APUESTA: ${bet_decision['amount']} | {bet_decision['rationale']} | TC:{tc_for_bet:.1f}"
            )

            if bet_decision.get("should_sit"):
                thinking_context["state"] = "sit_out"
                status_message = "Sentado"
                log_message += " | Sit out"

            self._emit_status_update(
                {
                    "log": log_message,
                    "status": status_message,
                },
                thinking_context,
            )

            if bet_decision.get("should_sit"):
                return

            self.last_bet_amount = float(bet_decision.get("amount", 0))
            self._execute_bet_action_enhanced(bet_decision)
        except Exception as exc:  # pragma: no cover - runtime
            self._emit_status_update(
                {"log": f"Error en decisión de apuesta: {exc}", "status": "Error"},
                {
                    "mode": "bet",
                    "state": "error",
                    "error": str(exc),
                },
            )

    def _execute_play_action_enhanced(self, decision: Dict) -> None:
        """Ejecución mejorada de acciones de juego."""

        if not self.safety_wrapper:
            return

        try:
            action_request = {
                "type": "PLAY",
                "payload": {
                    "move": decision["action"].value,
                    "confidence": decision["confidence"],
                    "tc_context": decision.get("tc_used", 0),
                },
            }

            confirmation = self.safety_wrapper.safe_execute(action_request)
            self.logger.log(confirmation)
            self.session_stats["actions_executed"] += 1

            ok = confirmation.get("ok", False)
            self.health_monitor.update_action_result(bool(ok))

            if ok:
                self._emit_status_update(
                    {
                        "log": f"M4 ✅ {decision['action'].value} ejecutado correctamente",
                        "status": "Acción ejecutada",
                        "last_action": decision["action"].value,
                        "action_time": time.time(),
                    }
                )
                if self.game_state:
                    self.game_state.last_decision = decision["action"].value
                self.safety_checks["last_successful_action"] = time.time()
            else:
                error = confirmation.get("error", "Error desconocido")
                self._emit_status_update(
                    {"log": f"M4 ❌ Error: {error}", "status": "Error de ejecución"}
                )
                if self.emergency_settings.get("safety", {}).get(
                    "auto_recalibration_enabled", True
                ) and self.actuator:
                    self.actuator.trigger_recalibration()
        except Exception as exc:  # pragma: no cover - seguridad adicional
            self._emit_status_update(
                {"log": f"Error ejecutando acción: {exc}", "status": "Error"}
            )

    def _execute_bet_action_enhanced(self, bet_decision: Dict) -> None:
        """Ejecución mejorada de acciones de apuesta."""

        if not self.safety_wrapper:
            return

        try:
            amount = float(bet_decision.get("amount", 0))
            if amount <= 0:
                self._emit_status_update(
                    {"log": "No se requiere apuesta para esta ronda", "status": "Sentado"}
                )
                return

            chip_plan = self._plan_bet_clicks_enhanced(amount)
            payload: Dict[str, Union[float, int, str, List[Dict[str, Union[int, str]]]]] = {
                "amount": amount,
                "units": bet_decision.get("units"),
            }

            if chip_plan:
                payload["chip_plan"] = chip_plan
                payload["chip_type"] = chip_plan[0]["chip_type"]
            else:
                chip_action = self._select_bet_chip_enhanced(amount)
                if not chip_action:
                    self._emit_status_update(
                        {"log": "No hay fichas disponibles para la apuesta", "status": "Error de apuesta"}
                    )
                    return
                payload["chip_type"] = chip_action

            action_request = {"type": "BET", "payload": payload}
            confirmation = self.safety_wrapper.safe_execute(action_request)
            self.logger.log(confirmation)
            self.session_stats["actions_executed"] += 1

            ok = confirmation.get("ok", False)
            self.health_monitor.update_action_result(bool(ok))

            if ok:
                self._emit_status_update(
                    {
                        "log": f"M4 ✅ Apuesta de ${amount} ejecutada correctamente",
                        "status": "Apuesta realizada",
                        "last_bet": amount,
                        "bet_time": time.time(),
                    }
                )
                self.safety_checks["last_successful_action"] = time.time()
            else:
                error = confirmation.get("error", "Error desconocido")
                self._emit_status_update(
                    {"log": f"M4 ❌ Error en apuesta: {error}", "status": "Error de apuesta"}
                )
        except Exception as exc:  # pragma: no cover - seguridad adicional
            self._emit_status_update(
                {"log": f"Error ejecutando apuesta: {exc}", "status": "Error"}
            )

    def _plan_bet_clicks_enhanced(self, amount: float) -> List[Dict[str, Union[int, str]]]:
        """Planificación mejorada de clics en fichas."""

        if not self.actuator or amount <= 0:
            return []

        available_chips = [("BET_100", 100), ("BET_25", 25)]
        plan: List[Dict[str, Union[int, str]]] = []
        remaining = int(round(amount))

        for chip_type, value in available_chips:
            if value <= remaining:
                count = remaining // value
                if count > 0:
                    plan.append({"chip_type": chip_type, "count": count})
                    remaining -= value * count

        if remaining > 0 and plan:
            smallest_chip = available_chips[-1]
            plan.append({"chip_type": smallest_chip[0], "count": 1})

        return plan

    def _select_bet_chip_enhanced(self, amount: float) -> Optional[str]:
        """Selección mejorada de ficha para apuesta."""

        if amount >= 100:
            return "BET_100"
        if amount >= 25:
            return "BET_25"
        return "BET_25"

    def _update_bankroll_enhanced(self, event: Event) -> None:
        """Actualización mejorada del bankroll."""

        if not (self.bankroll_tracker and self.rois):
            return

        if event.event_type not in (EventType.STATE_TEXT, EventType.ROUND_END):
            return

        bankroll_roi = self.rois.get("bankroll_area")
        if not bankroll_roi:
            return

        try:
            if self.vision and self.vision.last_frame is not None:
                bankroll_image = bankroll_roi.extract(self.vision.last_frame)
                if bankroll_image.size > 0:
                    current_bankroll, updated = self.bankroll_tracker.update_from_roi(
                        bankroll_image, self.last_bet_amount
                    )
                    if updated:
                        metrics = self.bankroll_tracker.get_financial_metrics()
                        self._last_financial_metrics = metrics

                        if self.decision_maker:
                            self.decision_maker.risk_manager.update_bankroll(metrics["bankroll"])

                        payload = {
                            "bankroll": metrics["bankroll"],
                            "pnl": metrics["pnl"],
                            "pnl_pct": metrics["pnl_pct"],
                            "drawdown": metrics["current_drawdown"],
                            "drawdown_pct": metrics["current_drawdown_pct"],
                            "max_drawdown": metrics["max_drawdown"],
                            "max_drawdown_pct": metrics["max_drawdown_pct"],
                            "bankroll_trend": self.bankroll_tracker.get_trend(),
                            "financial_metrics": metrics,
                        }

                        self._emit_status_update(payload)
        except Exception as exc:  # pragma: no cover - OCR externo
            print(f"Error actualizando bankroll: {exc}")
            if self.health_monitor:
                self.health_monitor.increment_bankroll_failure()

    def _update_health_from_event(self, event: Event) -> None:
        """Actualización de salud del sistema desde eventos."""

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
        """Emite reporte de salud periódicamente."""

        if not self.health_monitor:
            return

        interval = self.emergency_settings.get("safety", {}).get("health_check_interval", 60)
        if time.time() - self._last_health_report < interval:
            return

        health_report = self.health_monitor.generate_health_report()
        health_report["session_stats"] = self.session_stats.copy()
        health_report["session_stats"]["uptime"] = time.time() - self.session_stats["start_time"]

        if self.actuator:
            health_report["actuator_status"] = self.actuator.get_status()
        if self.safety_wrapper:
            health_report["safety_status"] = self.safety_wrapper.get_safety_status()
        if self.vision:
            health_report["vision_status"] = self.vision.get_detection_status()
        if self._last_financial_metrics:
            health_report["financial_metrics"] = self._last_financial_metrics

        socketio.emit("health_update", health_report)
        self._last_health_report = time.time()

    def get_system_status(self) -> Dict:
        """Obtiene estado completo del sistema mejorado."""

        status = {
            "timestamp": time.time(),
            "window_info": self.window_info,
            "rois_count": len(self.rois),
            "session_stats": self.session_stats.copy(),
            "emergency_settings": self.emergency_settings,
            "safety_checks": self.safety_checks.copy(),
        }

        if self.counter:
            status["counter_status"] = self.counter.get_snapshot()
        if self.decision_maker:
            status["decision_status"] = self.decision_maker.get_status()
        if self.game_state:
            status["game_status"] = self.game_state.get_state()
        if self.fsm:
            status["fsm_status"] = self.fsm.get_state()

        if self._last_financial_metrics:
            status["financial_metrics"] = self._last_financial_metrics
        if self._last_thinking:
            status["last_thinking"] = self._last_thinking

        return status


def enhanced_bot_worker(config: Optional[Dict]) -> None:
    """Worker del bot con mejoras implementadas."""

    global bot_running, current_orchestrator
    print("🚀 Iniciando worker del bot mejorado...")

    try:
        orchestrator = EnhancedBotOrchestrator(config)
        with orchestrator_lock:
            current_orchestrator = orchestrator
        orchestrator.run()
    except Exception as exc:  # pragma: no cover - worker runtime
        socketio.emit(
            "status_update",
            {"log": f"ERROR CRÍTICO: {exc}", "status": "Error crítico"},
        )
        print(f"Error crítico en bot worker: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        bot_running = False
        with orchestrator_lock:
            current_orchestrator = None


def _perform_enhanced_calibration() -> Dict[str, Any]:
    """Ejecuta la calibración y devuelve un resumen estructurado."""

    try:
        calibrator = ImprovedCalibrationTool()
        success = calibrator.run_enhanced_calibration()

        if success:
            return {
                "status": "Calibración exitosa",
                "success": True,
                "features": [
                    "Detección específica de All Bets Blackjack",
                    "Sistema híbrido coordenadas + template matching",
                    "ROIs preconfiguradas",
                ],
            }

        return {
            "status": "Calibración fallida",
            "success": False,
            "error": "Ver logs del sistema",
        }
    except Exception as exc:  # pragma: no cover - depende de entorno
        return {"status": "Error en calibración", "success": False, "error": str(exc)}


def _run_system_checks() -> Dict[str, Any]:
    """Ejecuta pruebas rápidas de estado y devuelve resultados agregados."""

    tests: List[Dict[str, Any]] = []
    passed = 0

    # Prueba de detección de ventana
    try:
        detector = GameWindowDetector()
        window = detector.get_game_window()
        success = window is not None
        tests.append(
            {
                "name": "Detección de ventana",
                "passed": success,
                "details": getattr(window, "title", "No encontrada") if window else "Ventana no encontrada",
            }
        )
        if success:
            passed += 1
    except Exception as exc:  # pragma: no cover - defensivo
        tests.append({"name": "Detección de ventana", "passed": False, "details": str(exc)})

    # Prueba de orquestador de decisiones
    try:
        decision = DecisionOrchestrator(initial_bankroll=1000)
        status = decision.get_status()
        success = bool(status)
        tests.append(
            {
                "name": "Motor de decisiones",
                "passed": success,
                "details": f"Win rate base: {status.get('win_rate', 0):.2%}" if success else "Sin datos",
            }
        )
        if success:
            passed += 1
    except Exception as exc:  # pragma: no cover - defensivo
        tests.append({"name": "Motor de decisiones", "passed": False, "details": str(exc)})

    # Prueba de actuador y mouse humanizado
    try:
        actuator = HybridActuator()
        status = actuator.get_status()
        success = bool(status)
        tests.append(
            {
                "name": "Actuador híbrido",
                "passed": success,
                "details": f"Acciones disponibles: {len(status.get('available_actions', []))}",
            }
        )
        if success:
            passed += 1
    except Exception as exc:  # pragma: no cover - defensivo
        tests.append({"name": "Actuador híbrido", "passed": False, "details": str(exc)})

    # Prueba de métricas financieras
    try:
        tracker = BankrollTracker(initial_bankroll=1000)
        metrics = tracker.get_financial_metrics()
        success = metrics.get("bankroll") == 1000
        tests.append(
            {
                "name": "Métricas financieras",
                "passed": success,
                "details": f"P&L inicial: {metrics.get('pnl', 0):.2f}",
            }
        )
        if success:
            passed += 1
    except Exception as exc:  # pragma: no cover - defensivo
        tests.append({"name": "Métricas financieras", "passed": False, "details": str(exc)})

    total = len(tests)
    return {
        "success": passed == total and total > 0,
        "passed": passed,
        "total": total,
        "tests": tests,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/detect_window", methods=["POST"])
def detect_window() -> Dict[str, Any]:
    """Verifica el estado de la ventana de juego antes de iniciar el bot."""

    try:
        detector = GameWindowDetector()
        window = detector.get_game_window(force_refresh=True)

        if not window:
            return {
                "success": False,
                "error": "Ventana de All Bets Blackjack no encontrada",
                "timestamp": time.time(),
            }

        window_info = {
            "title": getattr(window, "title", ""),
            "width": getattr(window, "width", 0),
            "height": getattr(window, "height", 0),
            "left": getattr(window, "left", 0),
            "top": getattr(window, "top", 0),
        }

        return {
            "success": True,
            "window_title": window_info["title"],
            "window": window_info,
            "timestamp": time.time(),
        }
    except Exception as exc:  # pragma: no cover - defensivo
        return {"success": False, "error": str(exc), "timestamp": time.time()}


@app.route("/test_systems", methods=["POST"])
def test_systems() -> Dict[str, Any]:
    """Ejecuta pruebas rápidas para validar subsistemas críticos."""

    results = _run_system_checks()
    results["timestamp"] = time.time()
    return results


@app.route("/start", methods=["POST"])
def start_bot():
    global bot_thread, bot_running
    if not bot_running:
        bot_running = True
        config = request.get_json(silent=True) or {}
        config.setdefault("initial_bankroll", 1000)

        print(f"🎯 Iniciando bot con configuración mejorada: {config}")

        bot_thread = threading.Thread(
            target=enhanced_bot_worker,
            args=(config,),
            daemon=True,
            name="EnhancedBotWorker",
        )
        bot_thread.start()

        return {"status": "Bot iniciado", "config": config, "timestamp": time.time()}
    return {"status": "Bot ya está ejecutándose", "running": True, "timestamp": time.time()}


@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return {"status": "Deteniendo bot...", "running": False, "timestamp": time.time()}


@app.route("/run_calibration", methods=["POST"])
def run_enhanced_calibration():
    """Ejecuta calibración mejorada desde la web."""

    result = _perform_enhanced_calibration()
    result["timestamp"] = time.time()
    return result


@app.route("/calibrate", methods=["POST"])
def calibrate():
    """Alias simplificado para iniciar la calibración desde el panel."""

    result = _perform_enhanced_calibration()
    result["timestamp"] = time.time()
    return result


@app.route("/system_status", methods=["GET"])
def get_enhanced_system_status():
    """Obtiene estado detallado del sistema mejorado."""

    try:
        payload: Dict[str, Any] = {
            "system_type": "enhanced",
            "bot_running": bot_running,
            "timestamp": time.time(),
        }

        with orchestrator_lock:
            orchestrator = current_orchestrator

        if orchestrator:
            payload["status"] = "Bot ejecutándose"
            payload["details"] = orchestrator.get_system_status()
        else:
            payload["status"] = "Bot detenido"
            payload["details"] = {}

        # Estado de ventana en vivo para transparencia
        detector = GameWindowDetector()
        window = detector.get_game_window()
        payload["window_detected"] = bool(window)
        if window:
            payload["window_info"] = {
                "title": getattr(window, "title", ""),
                "width": getattr(window, "width", 0),
                "height": getattr(window, "height", 0),
            }

        return payload
    except Exception as exc:  # pragma: no cover - defensivo
        return {"error": str(exc), "timestamp": time.time()}


if __name__ == "__main__":
    print("🚀 Iniciando Panel de Control Mejorado en http://127.0.0.1:5000")
    print("✨ Mejoras implementadas:")
    print("   • Detección específica de 'All Bets Blackjack'")
    print("   • Sistema híbrido de coordenadas y template matching")
    print("   • Visión optimizada para formato compartido")
    print("   • Actuador robusto sin dependencia de calibración manual")

    socketio.run(app, host="127.0.0.1", port=5000, debug=False)
