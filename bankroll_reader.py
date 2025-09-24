"""Utility helpers to keep track of the bankroll displayed on screen."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

import cv2
import numpy as np
import pytesseract


@dataclass
class BankrollTracker:
    """Track bankroll readings extracted from on-screen regions.

    The tracker keeps a history of bankroll values and exposes a simple
    ``update_from_roi`` method that accepts an ROI image (as a NumPy array).
    It performs lightweight preprocessing and OCR to parse currency values.
    """

    initial_bankroll: float = 0.0
    history: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.current_bankroll = float(self.initial_bankroll)
        if not self.history:
            self.history.append(self.current_bankroll)

    def update_from_roi(self, roi_image: np.ndarray, last_bet_amount: float = 0.0) -> Tuple[float, bool]:
        """Parse the bankroll value from a ROI image.

        Args:
            roi_image: Screenshot fragment where the bankroll text is rendered.
            last_bet_amount: Not used yet but kept for compatibility with
                downstream callers that might rely on the signature.

        Returns:
            A tuple ``(current_bankroll, updated)`` where ``updated`` indicates
            whether a new bankroll value was successfully parsed.
        """

        if roi_image is None or getattr(roi_image, "size", 0) == 0:
            return self.current_bankroll, False

        text = self._read_bankroll_text(roi_image)
        if text is None:
            return self.current_bankroll, False

        parsed_value = self._parse_currency_value(text)
        if parsed_value is None:
            return self.current_bankroll, False

        if parsed_value != self.current_bankroll:
            self.current_bankroll = parsed_value
            self.history.append(parsed_value)
            return self.current_bankroll, True

        return self.current_bankroll, False

    def _read_bankroll_text(self, roi_image: np.ndarray) -> str | None:
        gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        try:
            ocr_result = pytesseract.image_to_string(
                thresh,
                config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789.,",
            )
        except pytesseract.TesseractError:
            return None

        text = ocr_result.strip()
        return text or None

    def _parse_currency_value(self, text: str) -> float | None:
        digits = re.sub(r"[^0-9.,]", "", text)
        if not digits:
            return None

        digits = digits.replace(",", "")
        try:
            return float(digits)
        except ValueError:
            return None
