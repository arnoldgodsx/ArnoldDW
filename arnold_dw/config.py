"""User settings persisted as JSON in the AppData config dir.

To add a setting: add a typed field with a default to `Settings`. Loading
validates each stored value against the type of its default, so a missing,
mistyped or corrupt entry silently falls back to the default. Bump
`SCHEMA_VERSION` and extend `_migrate` only when an existing key changes
meaning or shape.
"""

import dataclasses
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field

from arnold_dw import paths

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class Settings:
    download_dir: str = field(default_factory=paths.default_download_dir)
    max_concurrent: int = 2  # downloads running at the same time (clamped by core.jobs)

    def to_dict(self):
        return {"schema": SCHEMA_VERSION, **dataclasses.asdict(self)}

    @classmethod
    def from_dict(cls, data):
        settings = cls()
        if not isinstance(data, dict):
            return settings
        data = _migrate(data)
        for f in dataclasses.fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            default = getattr(settings, f.name)
            if _is_valid(value, default):
                setattr(settings, f.name, value)
            else:
                log.warning("Ignoring invalid setting %s=%r", f.name, value)
        return settings


def _is_valid(value, default):
    # bool is a subclass of int; don't let True/False pass for numeric settings or vice versa.
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(value, bool) and isinstance(default, bool)
    if isinstance(default, str):
        return isinstance(value, str) and bool(value.strip())
    if isinstance(default, float):
        return isinstance(value, (int, float))
    return isinstance(value, type(default))


def _migrate(data):
    schema = data.get("schema", 0)
    if not isinstance(schema, int):
        schema = 0
    if schema > SCHEMA_VERSION:
        log.warning("Config schema %s is newer than supported %s; reading known keys only",
                    schema, SCHEMA_VERSION)
    # schema 0 is the pre-package format: {"download_dir": "..."} - same key, nothing to rename.
    return data


def load_settings(path=None):
    path = path or paths.config_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError):
        log.warning("Could not read settings from %s; using defaults", path, exc_info=True)
        return Settings()
    return Settings.from_dict(data)


def save_settings(settings, path=None):
    """Atomically write settings (temp file + os.replace). Returns True on success."""
    path = path or paths.config_path()
    directory = os.path.dirname(path)
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
        return True
    except OSError:
        log.exception("Could not save settings to %s", path)
        return False
    finally:
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
