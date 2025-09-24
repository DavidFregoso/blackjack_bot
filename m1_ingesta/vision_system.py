"""Bucle principal de visión por computadora para el Módulo 1.

El `VisionSystem` captura la pantalla, reconoce cartas y lee el estado del
juego. Cada cambio detectado se comunica mediante eventos compatibles con
`utils.contratos.Event` para que los módulos posteriores puedan reaccionar.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Generator, Iterable, Iterator, List, Optional

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
            return np.zeros((0, 0, frame.shape[2] if frame.ndim == 3 else 1), dtype=frame.dtype)
        return frame[roi.top : roi.top + roi.height, roi.left : roi.left + roi.width]

    def to_mss(self) -> Dict[str, int]:
        """Convierte la ROI al formato utilizado por `mss`."""

        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


class VisionSystem:
    """Orquesta la captura de pantalla y la generación de eventos."""

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

        self.rois: Dict[str, RegionOfInterest] = {}
        for name, roi in rois.items():
            if isinstance(roi, RegionOfInterest):
                self.rois[name] = roi
            else:
                self.rois[name] = RegionOfInterest(**roi)

        self.last_state: Dict[str, Iterable[str] | str] = {
            "dealer_cards": [],
            "player_cards": [],
            "game_status": "",
        }

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def run(self) -> Iterator[Event]:
        """Generador de eventos detectados en tiempo real."""

        self._running = True
        try:
            while self._running:
                frame, events = self.capture()

                for event in events:
                    yield event

                time.sleep(self.poll_interval)
        finally:
            self._running = False

    def stop(self) -> None:
        """Detiene el bucle en la siguiente iteración."""

        self._running = False

    def capture(self) -> tuple[np.ndarray, List[Event]]:
        """Captura un frame y retorna los eventos detectados."""

        frame = self._grab_frame()
        events = list(self._process_frame(frame))
        return frame, events

    # ------------------------------------------------------------------
    # Procesamiento de cada frame
    # ------------------------------------------------------------------
    def _process_frame(self, frame: np.ndarray) -> Generator[Event, None, None]:
        dealer_cards = self._recognize_cards(frame, "dealer_cards")
        if dealer_cards is not None:
            yield from self._emit_card_events("dealer_cards", dealer_cards)

        player_cards = self._recognize_cards(frame, "player_cards")
        if player_cards is not None:
            yield from self._emit_card_events("player_cards", player_cards)

        status_text = self._read_status_text(frame)
        if status_text is not None:
            last_status = self.last_state.get("game_status", "")
            if status_text != last_status:
                yield Event.create(
                    EventType.STATE_TEXT,
                    round_id=self.round_id,
                    text=status_text,
                )
                self.last_state["game_status"] = status_text

    def _grab_frame(self) -> np.ndarray:
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

    # ------------------------------------------------------------------
    # Reconocimiento de cartas
    # ------------------------------------------------------------------
    def _recognize_cards(self, frame: np.ndarray, roi_key: str) -> Optional[List[str]]:
        roi = self.rois.get(roi_key)
        if roi is None:
            return None

        roi_image = roi.extract(frame)
        if roi_image.size == 0:
            return []

        cards = self.recognizer.recognize_cards_in_roi(roi_image)
        return cards

    def _emit_card_events(
        self, key: str, cards: List[str]
    ) -> Generator[Event, None, None]:
        last_cards = list(self.last_state.get(key, []))
        if cards != last_cards:
            new_cards = CardRecognizer.diff_cards(last_cards, cards)
            if new_cards:
                yield Event.create(
                    EventType.CARD_DEALT_SHARED,
                    round_id=self.round_id,
                    target=key,
                    cards=new_cards,
                )
            self.last_state[key] = cards

    # ------------------------------------------------------------------
    # Lectura del estado del juego (OCR)
    # ------------------------------------------------------------------
    def _read_status_text(self, frame: np.ndarray) -> Optional[str]:
        roi = self.rois.get("game_status")
        if roi is None:
            return None

        roi_image = roi.extract(frame)
        if roi_image.size == 0:
            return ""

        gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        try:
            text = pytesseract.image_to_string(thresh, config="--psm 7 --oem 3")
        except TesseractNotFoundError:
            LOGGER.error(
                "Tesseract OCR no está instalado o no es accesible. Consulta la documentación."
            )
            return ""
        except pytesseract.TesseractError as exc:
            LOGGER.debug("Error de OCR: %s", exc)
            return ""

        normalized = text.strip().lower()
        return normalized
