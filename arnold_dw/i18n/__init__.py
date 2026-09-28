"""Thread-safe, UI-independent translation helpers."""

from __future__ import annotations

import ctypes
import json
import logging
import threading
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)
_LOCK = threading.RLock()
_LANGUAGE: str | None = None
_MISSING: set[str] = set()
_LANGUAGES = ("tr", "en")
_CATALOG_DIR = Path(__file__).parent


@cache
def _catalog(code: str) -> dict[str, str]:
    try:
        with (_CATALOG_DIR / f"{code}.json").open(encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        log.exception("Could not load %s translation catalog", code)
        return {}


def available_languages() -> tuple[str, ...]:
    """Return supported language codes."""
    return _LANGUAGES


def _system_language() -> str:
    try:
        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        primary_language = language_id & 0x3FF
        return "tr" if primary_language == 0x1F else "en"
    except (AttributeError, OSError, TypeError, ValueError):
        return "en"


def current_language() -> str:
    """Return the selected language, detecting the Windows UI language once."""
    global _LANGUAGE
    with _LOCK:
        if _LANGUAGE is None:
            _LANGUAGE = _system_language()
        return _LANGUAGE


def set_language(code: str) -> None:
    """Select ``tr`` or ``en``. Unsupported codes raise ValueError."""
    normalized = str(code).strip().lower().replace("_", "-").split("-", 1)[0]
    if normalized not in _LANGUAGES:
        raise ValueError(f"Unsupported language: {code}")
    global _LANGUAGE
    with _LOCK:
        _LANGUAGE = normalized


def _format(template: str, params: dict) -> str:
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError, TypeError):
        return template


def t(key: str, **params) -> str:
    """Translate a key, falling back to Turkish and then to the key itself."""
    language = current_language()
    requested_key = key
    if "count" in params and not key.endswith((".one", ".other")):
        requested_key = f"{key}.{'one' if params['count'] == 1 else 'other'}"

    value = _catalog(language).get(requested_key)
    if value is None:
        value = _catalog("tr").get(requested_key)
    if value is None:
        with _LOCK:
            if requested_key not in _MISSING:
                log.warning("Missing translation key: %s", requested_key)
                _MISSING.add(requested_key)
        value = requested_key
    return _format(value, params)


__all__ = ["t", "set_language", "current_language", "available_languages"]
