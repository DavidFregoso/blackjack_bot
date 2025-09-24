"""Utilidades para detectar y configurar Tesseract OCR.

Este módulo centraliza la lógica utilizada por los scripts de instalación y
verificación para localizar el ejecutable de Tesseract en diferentes sistemas
operativos. También permite persistir una ruta manual proporcionada por la
persona usuaria en ``configs/tesseract_path.txt`` para reutilizarla en futuras
ejecuciones.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Iterator, Optional, Tuple

try:  # pragma: no cover - se evalúa según la instalación del usuario
    import pytesseract
except ImportError:  # pragma: no cover - el módulo es opcional durante la instalación
    pytesseract = None  # type: ignore

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "configs"
TESSERACT_PATH_FILE = CONFIG_DIR / "tesseract_path.txt"
EXECUTABLE_NAME = "tesseract.exe" if os.name == "nt" else "tesseract"


def _normalize_candidate(raw_path: str | Path) -> Optional[Path]:
    """Convierte una ruta a un posible ejecutable de Tesseract.

    La persona usuaria puede proporcionar tanto la carpeta de instalación como
    la ruta directa al ejecutable. Esta función homogeneiza el formato para
    validar su existencia posteriormente.
    """

    raw_str = str(raw_path).strip().strip('"')
    if not raw_str:
        return None

    expanded = os.path.expanduser(os.path.expandvars(raw_str))
    candidate = Path(expanded)

    # Si ya apunta al ejecutable, devolverlo directamente.
    lower_name = candidate.name.lower()
    if lower_name == EXECUTABLE_NAME.lower():
        return candidate

    # Si la ruta contiene una extensión diferente, asumir que ya es un archivo.
    if candidate.suffix and lower_name != "tesseract":
        return candidate

    # En Windows preferimos terminar siempre en ``tesseract.exe``.
    if os.name == "nt":
        if lower_name == "tesseract":
            return candidate.with_name(EXECUTABLE_NAME)
        return candidate / EXECUTABLE_NAME

    # En sistemas Unix basta con terminar en ``tesseract``.
    if lower_name == "tesseract":
        return candidate
    return candidate / EXECUTABLE_NAME


def _read_stored_path() -> Optional[Path]:
    """Lee la ruta guardada manualmente, si existe."""

    if not TESSERACT_PATH_FILE.exists():
        return None

    try:
        stored = TESSERACT_PATH_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    candidate = _normalize_candidate(stored)
    if candidate and candidate.exists():
        return candidate

    return None


def _windows_registry_paths() -> list[Path]:  # pragma: no cover - depende del SO
    """Obtiene rutas potenciales desde el registro de Windows."""

    if os.name != "nt":
        return []

    try:
        import winreg  # type: ignore
    except ImportError:
        return []

    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tesseract-OCR"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Tesseract-OCR"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tesseract-OCR"),
    ]

    paths: list[Path] = []
    for hive, key_path in registry_keys:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
        except OSError:
            continue
        else:
            normalized = _normalize_candidate(install_dir)
            if normalized:
                paths.append(normalized)

    return paths


def _candidate_paths() -> Iterator[Tuple[Path, str]]:
    """Genera posibles ubicaciones del ejecutable y su origen."""

    seen: set[str] = set()

    def add_candidate(raw: str | Path, source: str) -> None:
        candidate = _normalize_candidate(raw)
        if candidate is None:
            return
        key = str(candidate).lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append((candidate, source))

    candidates: list[Tuple[Path, str]] = []

    stored = _read_stored_path()
    if stored:
        add_candidate(stored, "config file")

    env_cmd = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH")
    if env_cmd:
        add_candidate(env_cmd, "environment variable")

    detected = shutil.which("tesseract")
    if detected:
        add_candidate(Path(detected), "system PATH")

    system = platform.system().lower()
    if system == "windows":  # pragma: no cover - depende del SO
        add_candidate(r"C:\\Program Files\\Tesseract-OCR", "default installation path")
        add_candidate(
            r"C:\\Program Files (x86)\\Tesseract-OCR", "default installation path"
        )

        env_vars = ["PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "LOCALAPPDATA"]
        for var in env_vars:
            base_dir = os.environ.get(var)
            if base_dir:
                add_candidate(
                    Path(base_dir) / "Tesseract-OCR", f"environment variable {var}"
                )

        home = Path.home()
        add_candidate(
            home / "AppData" / "Local" / "Programs" / "Tesseract-OCR",
            "user installation",
        )
        add_candidate(home / "AppData" / "Local" / "Tesseract-OCR", "user installation")

        for registry_candidate in _windows_registry_paths():
            add_candidate(registry_candidate, "windows registry")
    elif system == "darwin":  # pragma: no cover - depende del SO
        add_candidate("/opt/homebrew/bin/tesseract", "homebrew")
        add_candidate("/usr/local/bin/tesseract", "usr local")
    else:  # Linux y otros sistemas Unix
        add_candidate("/usr/bin/tesseract", "system path")
        add_candidate("/usr/local/bin/tesseract", "system path")

    for candidate, source in candidates:
        yield candidate, source


def detect_tesseract_executable() -> Tuple[Optional[Path], Optional[str]]:
    """Intenta localizar el ejecutable de Tesseract."""

    for candidate, source in _candidate_paths():
        if candidate.exists():
            return candidate, source

    return None, None


def configure_pytesseract() -> Tuple[bool, Optional[Path], Optional[str]]:
    """Configura ``pytesseract`` con la ruta detectada.

    Devuelve una tupla ``(configurado, ruta, origen)``. Si ``pytesseract`` no
    está instalado, el valor de retorno será ``(False, None, None)``.
    """

    if pytesseract is None:
        return False, None, None

    executable, source = detect_tesseract_executable()
    if executable is None:
        return False, None, source

    pytesseract.pytesseract.tesseract_cmd = str(executable)

    parent = str(executable.parent)
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep) if current_path else []
    if parent not in paths:
        os.environ["PATH"] = parent + (
            os.pathsep + current_path if current_path else ""
        )

    return True, executable, source


def validate_tesseract_path(raw_path: str) -> Optional[Path]:
    """Valida que la ruta proporcionada contenga un ejecutable válido."""

    candidate = _normalize_candidate(raw_path)
    if candidate and candidate.exists():
        return candidate
    return None


def store_tesseract_path(path: Path) -> Path:
    """Guarda una ruta manual para reutilizarla en futuras ejecuciones."""

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_candidate(path)
    if normalized is None:
        raise ValueError("Ruta de Tesseract inválida")

    TESSERACT_PATH_FILE.write_text(str(normalized), encoding="utf-8")
    return normalized


__all__ = [
    "TESSERACT_PATH_FILE",
    "configure_pytesseract",
    "detect_tesseract_executable",
    "store_tesseract_path",
    "validate_tesseract_path",
]
