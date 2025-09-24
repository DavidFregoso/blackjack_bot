"""Sistema de visión optimizado para mesas compartidas All Bets Blackjack."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Generator, Iterator, List, Optional, Set, Tuple

import cv2
import mss
import numpy as np
import pytesseract
from pytesseract import TesseractNotFoundError

from utils.contratos import Event, EventType

from .card_recognizer import CardRecognizer

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegionOfInterest:
    """Define un rectángulo dentro del monitor a capturar."""

    left: int
    top: int
    width: int
    height: int

    def clamp(self, frame: np.ndarray) -> "RegionOfInterest":
        """Devuelve una ROI asegurando que quede dentro de la imagen."""

        if frame.size == 0:
            return self

        frame_h, frame_w = frame.shape[:2]
        left = max(self.left, 0)
        top = max(self.top, 0)
        right = min(self.left + self.width, frame_w)
        bottom = min(self.top + self.height, frame_h)
        width = max(right - left, 0)
        height = max(bottom - top, 0)
        return RegionOfInterest(left=left, top=top, width=width, height=height)

    def extract(self, frame: np.ndarray) -> np.ndarray:
        """Extrae la subimagen correspondiente a la ROI."""

        roi = self.clamp(frame)
        if roi.width == 0 or roi.height == 0:
            channels = frame.shape[2] if frame.ndim == 3 else 1
            return np.zeros((0, 0, channels), dtype=frame.dtype)
        return frame[roi.top : roi.top + roi.height, roi.left : roi.left + roi.width]

    def to_mss(self) -> Dict[str, int]:
        """Convierte la ROI al formato utilizado por `mss`."""

        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


class AllBetsBlackjackVision:
    """Sistema de visión optimizado para All Bets Blackjack."""

    def __init__(
        self,
        rois: Dict[str, RegionOfInterest | Dict[str, int]],
        *,
        monitor_index: int = 1,
        poll_interval: float = 0.5,
        round_id: Optional[str] = None,
        recognizer: Optional[CardRecognizer] = None,
    ) -> None:
        self.sct = mss.mss()
        self.monitor_index = monitor_index
        self.poll_interval = poll_interval
        self.round_id = round_id
        self.recognizer = recognizer or CardRecognizer()
        self._running = False
        self.last_frame: Optional[np.ndarray] = None

        # Convertir ROIs a formato estándar
        self.rois: Dict[str, RegionOfInterest] = {}
        for name, roi in rois.items():
            if isinstance(roi, RegionOfInterest):
                self.rois[name] = roi
            else:
                self.rois[name] = RegionOfInterest(**roi)

        # Estado específico para All Bets Blackjack
        self.last_state: Dict[str, Any] = {
            "dealer_cards": [],
            "player_cards": [],  # Cartas de la mano compartida
            "others_cards": set(),  # Set para evitar duplicados de cartas de divisiones
            "game_status": "",
            "phase": "idle",
        }

        # Cache para detección de cambios
        self.card_detection_cache: Dict[str, Tuple[Any, float]] = {}
        self.cache_duration = 2.0  # 2 segundos de cache

        # Configuración específica para All Bets
        self.config = {
            "shared_hand_enabled": True,
            "track_others_cards": True,
            "min_confidence": 0.8,
            "stable_frames_required": 2,
            "max_cards_per_detection": 8,
        }

        # Contador de frames estables para confirmación
        self.stable_frames: Dict[str, int] = {}
        self._stable_candidates: Dict[str, Any] = {}
        self.min_stable_frames = self.config["stable_frames_required"]

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def run(self) -> Iterator[Event]:
        """Generador de eventos detectados en tiempo real."""

        self._running = True
        try:
            frame_count = 0
            while self._running:
                frame, events = self.capture()

                for event in events:
                    yield event

                frame_count += 1
                if frame_count % 20 == 0:
                    LOGGER.debug(
                        "Processed %s frames, generated %s events", frame_count, len(events)
                    )

                time.sleep(self.poll_interval)
        finally:
            self._running = False

    def stop(self) -> None:
        """Detiene el bucle en la siguiente iteración."""

        self._running = False

    def capture(self) -> Tuple[np.ndarray, List[Event]]:
        """Captura un frame y retorna los eventos detectados."""

        frame = self._grab_frame()
        events = list(self._process_frame_enhanced(frame))
        return frame, events

    # ------------------------------------------------------------------
    # Procesamiento de frame mejorado
    # ------------------------------------------------------------------
    def _process_frame_enhanced(self, frame: np.ndarray) -> Generator[Event, None, None]:
        """Procesamiento mejorado para All Bets Blackjack."""

        # 1. Detectar cartas del crupier
        yield from self._process_dealer_cards(frame)

        # 2. Detectar cartas de la mano compartida (jugador principal)
        yield from self._process_shared_hand_cards(frame)

        # 3. Detectar cartas de otros jugadores / divisiones
        if self.config.get("track_others_cards", False):
            yield from self._process_others_cards(frame)

        # 4. Detectar estado del juego
        yield from self._process_game_status(frame)

    def _process_dealer_cards(self, frame: np.ndarray) -> Generator[Event, None, None]:
        """Procesa cartas del crupier con cache inteligente."""

        roi_key = "dealer_cards"
        if roi_key not in self.rois:
            return

        current_time = time.time()
        cached = self.card_detection_cache.get(roi_key)
        if cached and current_time - cached[1] < self.cache_duration:
            return

        new_cards = self._detect_cards_in_roi(frame, roi_key)
        if new_cards is None:
            return

        self.card_detection_cache[roi_key] = (list(new_cards), current_time)

        last_cards = self.last_state.get("dealer_cards", [])
        if new_cards != last_cards and self._is_change_stable(roi_key, new_cards):
            yield from self._emit_card_events("dealer_cards", new_cards, last_cards)
            self.last_state["dealer_cards"] = new_cards

    def _process_shared_hand_cards(self, frame: np.ndarray) -> Generator[Event, None, None]:
        """Procesa cartas de la mano compartida."""

        roi_key = "player_cards"
        if roi_key not in self.rois:
            return

        current_time = time.time()
        cached = self.card_detection_cache.get(roi_key)
        if cached and current_time - cached[1] < self.cache_duration:
            return

        new_cards = self._detect_cards_in_roi(frame, roi_key)
        if new_cards is None:
            return

        self.card_detection_cache[roi_key] = (list(new_cards), current_time)

        last_cards = self.last_state.get("player_cards", [])
        if new_cards != last_cards and self._is_change_stable(roi_key, new_cards):
            yield from self._emit_shared_hand_events(new_cards, last_cards)
            self.last_state["player_cards"] = new_cards

    def _process_others_cards(self, frame: np.ndarray) -> Generator[Event, None, None]:
        """Procesa cartas de otros jugadores y divisiones."""

        roi_key = "others_cards_area"
        if roi_key not in self.rois:
            return

        current_time = time.time()
        cached = self.card_detection_cache.get(roi_key)
        if cached and current_time - cached[1] < self.cache_duration:
            return

        max_cards = self.config.get("max_cards_per_detection")
        new_cards = self._detect_cards_in_roi(frame, roi_key, max_cards=max_cards)
        if new_cards is None:
            return

        self.card_detection_cache[roi_key] = (list(new_cards), current_time)

        last_others_set: Set[str] = self.last_state.get("others_cards", set())
        new_others_set: Set[str] = set(new_cards)

        if new_others_set != last_others_set and self._is_change_stable(
            roi_key, sorted(new_others_set)
        ):
            newly_seen = sorted(new_others_set - last_others_set)
            for card in newly_seen:
                yield Event.create(
                    EventType.CARD_DEALT,
                    round_id=self.round_id,
                    card=card,
                    who="others_overlay",
                    detection_source="others_area",
                )

            self.last_state["others_cards"] = new_others_set
        else:
            # Actualizar conjunto incluso si no hay cartas nuevas para evitar residuos
            self.last_state["others_cards"] = new_others_set

    def _process_game_status(self, frame: np.ndarray) -> Generator[Event, None, None]:
        """Procesa estado del juego con OCR mejorado."""

        roi_key = "game_status"
        if roi_key not in self.rois:
            return

        current_time = time.time()
        cached = self.card_detection_cache.get(roi_key)
        if cached and current_time - cached[1] < 1.0:
            return

        status_text = self._read_status_text_enhanced(frame, roi_key)
        if status_text is None:
            return

        self.card_detection_cache[roi_key] = (status_text, current_time)

        last_status = self.last_state.get("game_status", "")
        if status_text != last_status:
            detected_phase = self._determine_game_phase(status_text)
            yield Event.create(
                EventType.STATE_TEXT,
                round_id=self.round_id,
                text=status_text,
                phase=detected_phase,
                confidence=self.config.get("min_confidence", 0.0),
            )
            self.last_state["game_status"] = status_text
            self.last_state["phase"] = detected_phase

    # ------------------------------------------------------------------
    # Métodos de detección de cartas
    # ------------------------------------------------------------------
    def _detect_cards_in_roi(
        self, frame: np.ndarray, roi_key: str, max_cards: Optional[int] = None
    ) -> Optional[List[str]]:
        """Detecta cartas en una ROI específica."""

        roi = self.rois.get(roi_key)
        if roi is None:
            return None

        roi_image = roi.extract(frame)
        if roi_image.size == 0:
            return []

        try:
            cards = self.recognizer.recognize_cards_in_roi(roi_image)
        except Exception as exc:  # pragma: no cover - dep. de templates/entorno
            LOGGER.error("Error detecting cards in %s: %s", roi_key, exc)
            return None

        if max_cards is not None and len(cards) > max_cards:
            LOGGER.warning(
                "Too many cards detected in %s: %s, limiting to %s",
                roi_key,
                len(cards),
                max_cards,
            )
            cards = cards[:max_cards]

        valid_cards = [card for card in cards if self._is_valid_card(card)]
        for card in cards:
            if card not in valid_cards:
                LOGGER.debug("Invalid card filtered: %s", card)

        return valid_cards

    def _is_valid_card(self, card_str: str) -> bool:
        """Valida que una carta detectada sea válida."""

        if not card_str or len(card_str) < 2:
            return False

        if len(card_str) == 2:
            rank, suit = card_str[0], card_str[1]
        elif len(card_str) == 3 and card_str.startswith("10"):
            rank, suit = "T", card_str[2]
        else:
            return False

        valid_ranks = {"2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"}
        valid_suits = {"H", "D", "C", "S"}
        return rank in valid_ranks and suit in valid_suits

    def _normalize_for_stability(self, data: Any) -> Any:
        if isinstance(data, set):
            return tuple(sorted(data))
        if isinstance(data, list):
            return tuple(data)
        if isinstance(data, tuple):
            return data
        return data

    def _is_change_stable(self, roi_key: str, new_data: Any) -> bool:
        """Verifica si un cambio es estable a través de múltiples frames."""

        normalized = self._normalize_for_stability(new_data)
        candidate = self._stable_candidates.get(roi_key)
        if candidate != normalized:
            self._stable_candidates[roi_key] = normalized
            self.stable_frames[roi_key] = 1
            return False

        self.stable_frames[roi_key] = self.stable_frames.get(roi_key, 0) + 1
        if self.stable_frames[roi_key] >= self.min_stable_frames:
            self.stable_frames[roi_key] = 0
            self._stable_candidates.pop(roi_key, None)
            return True
        return False

    # ------------------------------------------------------------------
    # Emisión de eventos mejorada
    # ------------------------------------------------------------------
    def _emit_card_events(
        self, key: str, new_cards: List[str], last_cards: List[str]
    ) -> Generator[Event, None, None]:
        """Emite eventos de cartas con diferenciación mejorada."""

        if new_cards == last_cards:
            return

        added_cards = self._calculate_card_difference(last_cards, new_cards)
        if not added_cards:
            return

        if key == "dealer_cards":
            event_type = EventType.CARD_DEALT
            who = "dealer_up" if len(last_cards) == 0 else "dealer_draw"
        else:
            event_type = EventType.CARD_DEALT
            who = key

        for card in added_cards:
            yield Event.create(
                event_type,
                round_id=self.round_id,
                card=card,
                who=who,
                total_cards=len(new_cards),
                detection_region=key,
            )

    def _emit_shared_hand_events(
        self, new_cards: List[str], last_cards: List[str]
    ) -> Generator[Event, None, None]:
        """Emite eventos específicos para la mano compartida."""

        if new_cards == last_cards:
            return

        added_cards = self._calculate_card_difference(last_cards, new_cards)
        if not added_cards:
            return

        yield Event.create(
            EventType.CARD_DEALT_SHARED,
            round_id=self.round_id,
            cards=added_cards,
            who="player_shared",
            total_cards=len(new_cards),
            hand_type="shared",
        )
        LOGGER.debug(
            "Shared hand updated: %s -> %s, added: %s", last_cards, new_cards, added_cards
        )

    def _calculate_card_difference(self, old_cards: List[str], new_cards: List[str]) -> List[str]:
        """Calcula las cartas nuevas respetando multiplicidad."""

        from collections import Counter

        old_counter = Counter(old_cards)
        new_counter = Counter(new_cards)

        added: List[str] = []
        for card, count in new_counter.items():
            diff = count - old_counter.get(card, 0)
            if diff > 0:
                added.extend([card] * diff)
        return added

    # ------------------------------------------------------------------
    # OCR y detección de estado mejorado
    # ------------------------------------------------------------------
    def _read_status_text_enhanced(self, frame: np.ndarray, roi_key: str) -> Optional[str]:
        """OCR mejorado para detección de estado."""

        roi = self.rois.get(roi_key)
        if roi is None:
            return None

        roi_image = roi.extract(frame)
        if roi_image.size == 0:
            return ""

        try:
            processed_image = self._preprocess_for_ocr(roi_image)
            custom_config = (
                "--oem 3 --psm 6 "
                "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            )
            text = pytesseract.image_to_string(processed_image, config=custom_config)
            cleaned_text = self._clean_ocr_text(text)
            return cleaned_text
        except TesseractNotFoundError:
            LOGGER.error("Tesseract OCR no está instalado o no es accesible.")
            return ""
        except Exception as exc:  # pragma: no cover - depende de instalación OCR
            LOGGER.debug("Error en OCR: %s", exc)
            return ""

    def _preprocess_for_ocr(self, roi_image: np.ndarray) -> np.ndarray:
        """Preprocesamiento específico para OCR de texto de juego."""

        if len(roi_image.shape) == 3:
            gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_image.copy()

        height, width = gray.shape
        resized = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        denoised = cv2.bilateralFilter(resized, 9, 75, 75)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return cleaned

    def _clean_ocr_text(self, raw_text: str) -> str:
        """Limpia y normaliza texto de OCR."""

        if not raw_text:
            return ""

        import re

        cleaned = re.sub(r"[^\w\s\-\.\,\!]", " ", raw_text)
        cleaned = " ".join(cleaned.split())
        return cleaned.lower().strip()

    def _determine_game_phase(self, status_text: str) -> str:
        """Determina la fase del juego basada en el texto detectado."""

        if not status_text:
            return "idle"

        text_lower = status_text.lower()
        phase_patterns = {
            "bets_open": [
                "place your bets",
                "haz tu apuesta",
                "betting time",
                "place bets",
                "apostar",
                "betting",
            ],
            "dealing": [
                "dealing",
                "dealing cards",
                "repartiendo",
                "cards dealt",
                "cartas repartidas",
            ],
            "my_action": [
                "your turn",
                "tu turno",
                "player action",
                "make your move",
                "realiza tu jugada",
                "decide",
            ],
            "others_actions": [
                "other players",
                "otros jugadores",
                "waiting",
                "others playing",
                "esperando",
            ],
            "dealer_play": [
                "dealer",
                "crupier",
                "dealer turn",
                "turno del crupier",
                "dealer playing",
            ],
            "payouts": [
                "wins",
                "gana",
                "push",
                "empate",
                "bust",
                "blackjack",
                "results",
                "resultados",
                "payout",
            ],
        }

        for phase, patterns in phase_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return phase

        return "unknown"

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------
    def _grab_frame(self) -> np.ndarray:
        """Captura frame del monitor especificado."""

        monitors = self.sct.monitors
        try:
            monitor = monitors[self.monitor_index]
        except IndexError:
            LOGGER.error(
                "Monitor %s no disponible. Usando el monitor principal.",
                self.monitor_index,
            )
            monitor = monitors[0]

        screenshot = self.sct.grab(monitor)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        self.last_frame = frame
        return frame

    def get_last_frame(self) -> Optional[np.ndarray]:
        """Devuelve la última captura disponible."""

        if self.last_frame is None:
            return None
        return self.last_frame.copy()

    def get_detection_status(self) -> Dict[str, Any]:
        """Obtiene estado detallado del sistema de detección."""

        current_time = time.time()
        status = {
            "running": self._running,
            "monitor_index": self.monitor_index,
            "poll_interval": self.poll_interval,
            "round_id": self.round_id,
            "config": self.config.copy(),
            "last_state": {
                "dealer_cards": list(self.last_state.get("dealer_cards", [])),
                "player_cards": list(self.last_state.get("player_cards", [])),
                "others_cards": list(self.last_state.get("others_cards", [])),
                "game_status": self.last_state.get("game_status", ""),
                "phase": self.last_state.get("phase", "idle"),
            },
            "rois_configured": list(self.rois.keys()),
            "cache_status": {},
        }

        for roi_key, (data, cache_time) in self.card_detection_cache.items():
            age = current_time - cache_time
            size = len(data) if isinstance(data, (list, set, str, tuple)) else 1
            status["cache_status"][roi_key] = {
                "age_seconds": age,
                "is_valid": age < self.cache_duration,
                "data_type": type(data).__name__,
                "data_size": size,
            }
        return status

    def reset_detection_state(self) -> None:
        """Reinicia el estado de detección (útil al cambiar de ronda)."""

        self.last_state = {
            "dealer_cards": [],
            "player_cards": [],
            "others_cards": set(),
            "game_status": "",
            "phase": "idle",
        }
        self.card_detection_cache.clear()
        self.stable_frames.clear()
        self._stable_candidates.clear()
        LOGGER.info("Detection state reset")

    def update_round_id(self, new_round_id: str) -> None:
        """Actualiza el ID de ronda actual."""

        self.round_id = new_round_id

    def configure_for_all_bets_mode(self) -> None:
        """Configuración específica para modo All Bets Blackjack."""

        self.config.update(
            {
                "shared_hand_enabled": True,
                "track_others_cards": True,
                "min_confidence": 0.8,
                "stable_frames_required": 2,
                "max_cards_per_detection": 8,
            }
        )
        self.poll_interval = 0.4
        self.cache_duration = 1.5
        self.min_stable_frames = self.config["stable_frames_required"]
        LOGGER.info("Configured for All Bets Blackjack mode")


# Alias para mantener compatibilidad
VisionSystem = AllBetsBlackjackVision

__all__ = ["RegionOfInterest", "AllBetsBlackjackVision", "VisionSystem"]
