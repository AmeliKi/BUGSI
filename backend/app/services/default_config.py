import copy
import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_default_config: dict | None = None


def _load_default_config() -> dict:
    """Load default config from device-client/config/default.json."""
    # Docker: settings.DEVICE_CLIENT_DIR = /device-client
    # Local dev: fall back to sibling directory
    candidates = [
        Path(settings.DEVICE_CLIENT_DIR) / "config" / "default.json",
        Path(__file__).resolve().parents[3] / "device-client" / "config" / "default.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                config = json.load(f)
            logger.info("Loaded default device config from %s", path)
            return config

    logger.warning("Default device config not found, using empty config")
    return {}


def get_default_config() -> dict:
    """Return a deep copy of the default device config."""
    global _default_config
    if _default_config is None:
        _default_config = _load_default_config()
    return copy.deepcopy(_default_config)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_defaults(device_config: dict) -> dict:
    """Merge default config as base with device config as override.

    Missing keys from defaults are added; existing device values are preserved.
    """
    defaults = get_default_config()
    return _deep_merge(defaults, device_config)
