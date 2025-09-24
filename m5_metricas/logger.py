"""Módulo de logging para el sistema de Blackjack (Módulo 5)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict


class EventLogger:
    """Registra eventos en archivos ``.jsonl`` organizados por sesión."""

    def __init__(self, log_dir: str | Path = "logs/") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        session_timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.log_file = self.log_dir / f"session_{session_timestamp}.jsonl"
        print(f"[M5 Logger] Registrando eventos en: {self.log_file}")

    def log(self, event: Any) -> None:
        """Añade un evento al archivo de registro."""

        try:
            event_payload = self._prepare_event(event)
            with self.log_file.open("a", encoding="utf-8") as handler:
                json.dump(event_payload, handler, ensure_ascii=False)
                handler.write("\n")
        except Exception as exc:  # pragma: no cover - logging shouldn't stop the app
            print(f"⚠️ [M5 Logger] Error al escribir en el log: {exc}")

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------
    def _prepare_event(self, event: Any) -> Dict[str, Any]:
        if is_dataclass(event):
            event_dict = asdict(event)
        elif isinstance(event, dict):
            event_dict = dict(event)
        else:
            raise TypeError(
                "EventLogger.log solo acepta dataclasses compatibles o diccionarios."
            )

        serialized = {key: self._serialize(value) for key, value in event_dict.items()}

        # Asegurar la presencia de timestamp
        serialized.setdefault("timestamp", time.time())
        return serialized

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value

        if is_dataclass(value):
            return {key: self._serialize(field) for key, field in asdict(value).items()}

        if isinstance(value, dict):
            return {key: self._serialize(field) for key, field in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]

        if isinstance(value, Path):
            return str(value)

        return value


__all__ = ["EventLogger"]
