import json
import os
from pathlib import Path

_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "linux-toolbox"
_FILE = _DIR / "settings.json"


def _default_downloads() -> str:
    d = Path.home() / "Downloads"
    if not d.exists():
        d = Path.home() / "Downloads"
    return str(d / "Toolbox")


DEFAULTS = {
    "output_dir": _default_downloads(),
    "favorites": [],
    "recent": [],
    "whisper_model": "small",
    "llm_url": "http://127.0.0.1:11434",
    "llm_model": "qwen3:8b",
    "accent": "#7c6cff",
}

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = dict(DEFAULTS)
        try:
            _cache.update(json.loads(_FILE.read_text()))
        except Exception:
            pass
    return _cache


def get(key: str):
    return _load().get(key, DEFAULTS.get(key))


def put(key: str, value):
    _load()[key] = value
    _DIR.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(_cache, indent=2, ensure_ascii=False))


def all_() -> dict:
    return dict(_load())


def models_dir() -> Path:
    d = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "linux-toolbox" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d
