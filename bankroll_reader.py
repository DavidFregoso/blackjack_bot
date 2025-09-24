import re
import cv2
import numpy as np
import pytesseract
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class BankrollReader:
    """
    Lee y procesa el bankroll desde la pantalla usando OCR
    """

    def __init__(self):
        # Patrones comunes para texto de bankroll
        self.bankroll_patterns = [
            r"[\$\€\£]?\s*([0-9]+(?:[,\.][0-9]{3})*(?:\.[0-9]{2})?)",  # $1,234.56
            r"([0-9]+(?:[,\.][0-9]{3})*(?:\.[0-9]{2})?)\s*[\$\€\£]?",  # 1,234.56$
            r"Balance:\s*[\$\€\£]?\s*([0-9]+(?:[,\.][0-9]{3})*(?:\.[0-9]{2})?)",  # Balance: $1,234.56
            r"Saldo:\s*[\$\€\£]?\s*([0-9]+(?:[,\.][0-9]{3})*(?:\.[0-9]{2})?)",   # Saldo: $1,234.56
        ]

        # Configuración OCR optimizada para números
        self.ocr_config = '--psm 7 -c tessedit_char_whitelist=0123456789$,.€£ --oem 3'

    def read_bankroll_from_roi(self, roi_image: np.ndarray) -> Optional[float]:
        """
        Extrae el bankroll desde una imagen ROI usando OCR

        Args:
            roi_image: Imagen de la región donde aparece el bankroll

        Returns:
            Valor del bankroll como float, o None si no se puede leer
        """
        if roi_image is None or roi_image.size == 0:
            return None

        try:
            # Preprocesar imagen para mejorar OCR
            processed_image = self._preprocess_for_ocr(roi_image)

            # Aplicar OCR
            raw_text = pytesseract.image_to_string(processed_image, config=self.ocr_config)

            # Limpiar y procesar texto
            cleaned_text = raw_text.strip()
            logger.debug(f"OCR raw text: '{raw_text}' -> cleaned: '{cleaned_text}'")

            # Extraer valor numérico
            bankroll_value = self._extract_numeric_value(cleaned_text)

            if bankroll_value is not None:
                logger.info(f"Bankroll detected: ${bankroll_value:,.2f}")

            return bankroll_value

        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Error reading bankroll: {e}")
            return None

    def _preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocesa la imagen para mejorar la precisión del OCR
        """
        # Convertir a escala de grises si es necesario
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Redimensionar para mejorar OCR (2x más grande)
        height, width = gray.shape
        resized = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)

        # Aplicar filtro de ruido
        denoised = cv2.bilateralFilter(resized, 9, 75, 75)

        # Mejorar contraste usando CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Binarización adaptativa
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Morfología para limpiar texto
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        return cleaned

    def _extract_numeric_value(self, text: str) -> Optional[float]:
        """
        Extrae el valor numérico del texto del bankroll
        """
        if not text:
            return None

        # Intentar cada patrón
        for pattern in self.bankroll_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                number_str = matches[0]
                try:
                    # Limpiar formato de número
                    cleaned_number = self._clean_number_string(number_str)
                    return float(cleaned_number)
                except ValueError:
                    continue

        # Fallback: buscar cualquier número que parezca un monto
        fallback_pattern = r'([0-9]+(?:[,\.][0-9]{3})*(?:\.[0-9]{1,2})?)'
        matches = re.findall(fallback_pattern, text)

        if matches:
            # Tomar el número más largo (probablemente el bankroll)
            longest_match = max(matches, key=len)
            try:
                cleaned_number = self._clean_number_string(longest_match)
                potential_value = float(cleaned_number)

                # Filtrar valores que no parecen bankrolls realistas
                if 10.0 <= potential_value <= 1000000.0:  # Rango razonable
                    return potential_value

            except ValueError:
                pass

        return None

    def _clean_number_string(self, number_str: str) -> str:
        """
        Limpia una cadena numérica para convertir a float
        """
        # Remover espacios
        cleaned = number_str.replace(' ', '')

        # Manejar diferentes separadores decimales
        # Determinar si usa coma o punto como decimal
        if ',' in cleaned and '.' in cleaned:
            # Formato como 1,234.56 - punto es decimal
            cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            # Podría ser 1,234 (miles) o 1,56 (decimal)
            comma_parts = cleaned.split(',')
            if len(comma_parts) == 2 and len(comma_parts[1]) == 2:
                # Probablemente decimal: 1234,56 -> 1234.56
                cleaned = cleaned.replace(',', '.')
            elif len(comma_parts) > 2 or len(comma_parts[1]) == 3:
                # Probablemente miles: 1,234 o 1,234,567
                cleaned = cleaned.replace(',', '')

        return cleaned

    def validate_bankroll_change(self, old_bankroll: float, new_bankroll: float,
                                 recent_bet: float = 0) -> bool:
        """
        Valida si un cambio de bankroll es realista

        Args:
            old_bankroll: Bankroll anterior
            new_bankroll: Nuevo bankroll leído
            recent_bet: Apuesta reciente si se conoce

        Returns:
            True si el cambio parece válido
        """
        if old_bankroll <= 0 or new_bankroll <= 0:
            return False

        change = abs(new_bankroll - old_bankroll)
        change_percent = change / old_bankroll

        # Cambio muy grande (>50%) es sospechoso sin contexto
        if change_percent > 0.5 and recent_bet == 0:
            logger.warning(f"Large bankroll change detected: {old_bankroll} -> {new_bankroll}")
            return False

        # Si hay apuesta reciente, el cambio debería ser relacionado
        if recent_bet > 0:
            expected_change_min = recent_bet * 0.5   # Pérdida parcial
            expected_change_max = recent_bet * 2.5   # Ganancia con BJ

            if not (expected_change_min <= change <= expected_change_max):
                logger.warning(f"Bankroll change doesn't match bet: bet={recent_bet}, change={change}")
                return False

        return True


class BankrollTracker:
    """
    Rastrea el bankroll a lo largo del tiempo con validación y filtrado
    """

    def __init__(self, initial_bankroll: float = 0):
        self.reader = BankrollReader()
        self.current_bankroll = initial_bankroll
        self.history = [initial_bankroll] if initial_bankroll > 0 else []
        self.last_valid_reading = initial_bankroll
        self.consecutive_failures = 0
        self.max_failures = 3

    def update_from_roi(self, roi_image: np.ndarray, recent_bet: float = 0) -> Tuple[float, bool]:
        """
        Actualiza el bankroll desde una imagen ROI

        Args:
            roi_image: Imagen de la región del bankroll
            recent_bet: Apuesta reciente para validación

        Returns:
            Tuple de (bankroll_actual, lectura_exitosa)
        """
        new_reading = self.reader.read_bankroll_from_roi(roi_image)

        if new_reading is None:
            self.consecutive_failures += 1
            logger.warning(f"Failed to read bankroll ({self.consecutive_failures}/{self.max_failures})")

            # Si fallan muchas lecturas seguidas, mantener último valor válido
            if self.consecutive_failures >= self.max_failures:
                logger.error("Too many consecutive failures, using last valid reading")
                return self.last_valid_reading, False

            return self.current_bankroll, False

        # Validar lectura
        if self.current_bankroll > 0:
            is_valid = self.reader.validate_bankroll_change(
                self.current_bankroll, new_reading, recent_bet
            )

            if not is_valid:
                logger.warning(f"Invalid bankroll reading rejected: {new_reading}")
                return self.current_bankroll, False

        # Actualizar valores
        self.current_bankroll = new_reading
        self.last_valid_reading = new_reading
        self.history.append(new_reading)
        self.consecutive_failures = 0

        # Mantener historial limitado
        if len(self.history) > 100:
            self.history.pop(0)

        logger.info(f"Bankroll updated: ${new_reading:,.2f}")
        return new_reading, True

    def get_trend(self, periods: int = 5) -> str:
        """
        Obtiene la tendencia reciente del bankroll

        Returns:
            'increasing', 'decreasing', 'stable', o 'insufficient_data'
        """
        if len(self.history) < periods:
            return 'insufficient_data'

        recent_values = self.history[-periods:]
        first_val = recent_values[0]
        last_val = recent_values[-1]

        change_percent = (last_val - first_val) / first_val if first_val > 0 else 0

        if change_percent > 0.02:  # +2%
            return 'increasing'
        if change_percent < -0.02:  # -2%
            return 'decreasing'
        return 'stable'
