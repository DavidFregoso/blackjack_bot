"""Utilidades de visión para identificar cartas en la mesa.

El objetivo principal de este módulo es tomar una imagen (generalmente un
recorte de pantalla) y devolver las cartas detectadas en ella. La
implementación está pensada para trabajar con capturas del juego
"All Bets Blackjack" y utiliza una combinación de operaciones de visión
por computadora y *template matching*.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np

LOGGER = logging.getLogger(__name__)

# Alias para normalizar los nombres de archivos de plantillas.
_RANK_ALIASES: Dict[str, str] = {
    "10": "T",
    "0": "T",
    "t": "T",
    "jack": "J",
    "queen": "Q",
    "king": "K",
    "ace": "A",
}
_SUIT_ALIASES: Dict[str, str] = {
    "hearts": "H",
    "heart": "H",
    "diamonds": "D",
    "diamond": "D",
    "clubs": "C",
    "club": "C",
    "spades": "S",
    "spade": "S",
}


@dataclass
class CardDetection:
    """Representa una carta detectada dentro de una imagen."""

    rank: str
    suit: str
    score: float

    @property
    def label(self) -> str:
        """Etiqueta combinada de rango y palo."""

        return f"{self.rank}{self.suit}"


class CardRecognizer:
    """Detector de cartas basado en plantillas.

    La clase realiza tres tareas principales:

    1. Carga de plantillas (rango y palo) desde disco.
    2. Normalización de imágenes capturadas para aislar cada carta
       individual.
    3. Comparación del rango y el palo con las plantillas para obtener la
       carta más probable.

    Aunque el algoritmo está optimizado para las capturas del juego,
    muchos parámetros (área mínima de contorno, tamaño de carta resultante,
    umbrales, etc.) se exponen como atributos para facilitar la
    calibración.
    """

    def __init__(
        self,
        templates_path: str | Path = "m1_ingesta/templates",
        *,
        min_contour_area: int = 2000,
        card_size: Tuple[int, int] = (200, 300),
        match_threshold: float = 0.7,
    ) -> None:
        self.templates_path = Path(templates_path)
        self.min_contour_area = min_contour_area
        self.card_width, self.card_height = card_size
        self.match_threshold = match_threshold

        self.rank_templates = self._load_templates(self.templates_path / "ranks")
        self.suit_templates = self._load_templates(self.templates_path / "suits")

        if not self.rank_templates or not self.suit_templates:
            LOGGER.warning(
                "No se pudieron cargar todas las plantillas. Asegúrate de haber "
                "poblado 'templates/ranks' y 'templates/suits' con imágenes válidas."
            )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def recognize_cards_in_roi(self, roi_image: np.ndarray) -> List[str]:
        """Detecta y reconoce todas las cartas visibles en una región de interés.

        Parameters
        ----------
        roi_image:
            Imagen BGR que contiene una o varias cartas.

        Returns
        -------
        list[str]
            Lista de cartas detectadas en formato compacto (por ejemplo
            ``["AH", "7D"]``). La lista está ordenada de izquierda a
            derecha según la posición de la carta en la imagen original.
        """

        if roi_image is None or roi_image.size == 0:
            return []

        preprocessed = self._preprocess_for_contours(roi_image)
        contours, _ = cv2.findContours(
            preprocessed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return []

        sorted_contours = sorted(contours, key=lambda cnt: cv2.boundingRect(cnt)[0])
        detections: List[CardDetection] = []

        for contour in sorted_contours:
            if cv2.contourArea(contour) < self.min_contour_area:
                continue

            card_image = self._extract_card_image(roi_image, contour)
            if card_image is None:
                continue

            rank_roi, suit_roi = self._extract_rank_and_suit(card_image)
            if rank_roi is None or suit_roi is None:
                continue

            rank_match = self._match_template(rank_roi, self.rank_templates)
            suit_match = self._match_template(suit_roi, self.suit_templates)

            if rank_match is None or suit_match is None:
                continue

            detections.append(
                CardDetection(
                    rank=self._normalize_rank(rank_match.name),
                    suit=self._normalize_suit(suit_match.name),
                    score=min(rank_match.score, suit_match.score),
                )
            )

        return [detection.label for detection in detections]

    # ------------------------------------------------------------------
    # Carga y normalización de plantillas
    # ------------------------------------------------------------------
    def _load_templates(self, path: Path) -> Dict[str, np.ndarray]:
        templates: Dict[str, np.ndarray] = {}
        if not path.exists():
            LOGGER.warning("La ruta de plantillas '%s' no existe", path)
            return templates

        for file in path.glob("*.png"):
            template_img = cv2.imread(str(file), cv2.IMREAD_GRAYSCALE)
            if template_img is None:
                LOGGER.warning("No se pudo leer la plantilla: %s", file)
                continue

            processed = self._prepare_template(template_img)
            if processed is None:
                LOGGER.warning("No se pudo procesar la plantilla: %s", file)
                continue

            templates[file.stem] = processed

        return templates

    def _prepare_template(self, template: np.ndarray) -> Optional[np.ndarray]:
        if template is None or template.size == 0:
            return None

        if template.ndim == 3:
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        template = cv2.GaussianBlur(template, (3, 3), 0)
        _, template = cv2.threshold(
            template, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        return template

    # ------------------------------------------------------------------
    # Procesamiento de imágenes capturadas
    # ------------------------------------------------------------------
    def _preprocess_for_contours(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh = cv2.bitwise_not(thresh)
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        return thresh

    def _extract_card_image(
        self, image: np.ndarray, contour: np.ndarray
    ) -> Optional[np.ndarray]:
        if contour is None or len(contour) == 0:
            return None

        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        box = np.array(box, dtype="float32")

        ordered_box = self._order_points(box)
        destination = np.array(
            [
                [0, 0],
                [self.card_width - 1, 0],
                [self.card_width - 1, self.card_height - 1],
                [0, self.card_height - 1],
            ],
            dtype="float32",
        )

        matrix = cv2.getPerspectiveTransform(ordered_box, destination)
        warped = cv2.warpPerspective(image, matrix, (self.card_width, self.card_height))
        return warped

    def _extract_rank_and_suit(
        self, card_image: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        if card_image is None or card_image.size == 0:
            return None, None

        h, w = card_image.shape[:2]
        corner_w = max(int(w * 0.32), 1)
        corner_h = max(int(h * 0.40), 1)
        corner = card_image[0:corner_h, 0:corner_w]

        if corner.size == 0:
            return None, None

        gray = cv2.cvtColor(corner, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        split = max(int(thresh.shape[0] * 0.55), 1)
        rank_roi = thresh[0:split, :]
        suit_roi = thresh[split:, :]

        if rank_roi.size == 0 or suit_roi.size == 0:
            return None, None

        return rank_roi, suit_roi

    # ------------------------------------------------------------------
    # Template matching y utilidades
    # ------------------------------------------------------------------
    @dataclass
    class _TemplateMatch:
        name: str
        score: float

    def _match_template(
        self, image_roi: np.ndarray, templates: Dict[str, np.ndarray]
    ) -> Optional["CardRecognizer._TemplateMatch"]:
        if image_roi is None or image_roi.size == 0 or not templates:
            return None

        roi = image_roi
        if roi.ndim == 3:
            roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        roi = cv2.GaussianBlur(roi, (3, 3), 0)
        _, roi = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        best_match: Optional[CardRecognizer._TemplateMatch] = None
        for name, template in templates.items():
            if template is None or template.size == 0:
                continue

            resized_roi = cv2.resize(roi, (template.shape[1], template.shape[0]))
            try:
                result = cv2.matchTemplate(
                    resized_roi, template, cv2.TM_CCOEFF_NORMED
                )
            except cv2.error as exc:  # pragma: no cover - protección defensiva
                LOGGER.debug("Error durante el template matching: %s", exc)
                continue

            score = float(result.max()) if result.size else 0.0
            if score < self.match_threshold:
                continue

            if best_match is None or score > best_match.score:
                best_match = CardRecognizer._TemplateMatch(name=name, score=score)

        return best_match

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------
    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        if pts.shape[0] != 4:
            hull = cv2.convexHull(pts)
            if hull.shape[0] < 4:
                return pts
            pts = hull.reshape(-1, 2)[:4]

        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # Top-left
        rect[2] = pts[np.argmax(s)]  # Bottom-right

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # Top-right
        rect[3] = pts[np.argmax(diff)]  # Bottom-left

        return rect

    def _normalize_rank(self, name: str) -> str:
        normalized = _RANK_ALIASES.get(name.lower(), name.upper())
        if normalized == "10":
            return "T"
        if len(normalized) == 1 and normalized in "23456789TJQKA":
            return normalized
        return normalized[:1]

    def _normalize_suit(self, name: str) -> str:
        normalized = _SUIT_ALIASES.get(name.lower(), name[:1].upper())
        if normalized in {"H", "D", "C", "S"}:
            return normalized
        return normalized[:1].upper()

    # ------------------------------------------------------------------
    # Métodos utilitarios expuestos para pruebas o depuración
    # ------------------------------------------------------------------
    @staticmethod
    def diff_cards(previous: Iterable[str], current: Iterable[str]) -> List[str]:
        """Devuelve las cartas que aparecen en ``current`` y no en ``previous``.

        Se usa `Counter` para respetar las multiplicidades en caso de cartas
        duplicadas (por ejemplo, cuando el reconocimiento detecta dos manos).
        """

        prev_counter = Counter(previous)
        current_counter = Counter(current)
        diff: List[str] = []

        for card, count in current_counter.items():
            missing = count - prev_counter.get(card, 0)
            if missing > 0:
                diff.extend([card] * missing)

        return diff
