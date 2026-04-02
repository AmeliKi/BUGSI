from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"
_CREDENTIALS_PATH = "/mnt/usb/bugsi/credentials.json"
_LOCAL_CONFIG_PATH = "/mnt/usb/bugsi/config.json"
_HARDWARE_CONF_PATH = "/etc/bugsi/hardware.conf"

# Camera types per hardware configuration (set by install_hardware.sh)
_HW_CAMERA_OVERRIDES = {
    "A": {
        "still_camera": {
            "type": "ids_rgb",
            "exposure_us": 0,
            "gain_db": 0.0,
            "white_balance": "off",
            "balance_ratio_red": 1.2,
            "balance_ratio_green": 1.0,
            "balance_ratio_blue": 1.5,
        },
        "event_camera": {"type": "ids_evs"},
    },
    "B": {
        "still_camera": {"type": "arducam_64mp", "resolution_width": 3840, "resolution_height": 2160},
        "event_camera": {"type": "prophesee_genx320"},
    },
}


class ConfigManager:
    """Manages device configuration from remote SaaS, local fallback, and defaults."""

    def __init__(
        self,
        default_config_path: str | Path = _DEFAULT_CONFIG_PATH,
        local_config_path: str | Path = _LOCAL_CONFIG_PATH,
        credentials_path: str | Path = _CREDENTIALS_PATH,
    ):
        self._default_config_path = Path(default_config_path)
        self._local_config_path = Path(local_config_path)
        self._credentials_path = Path(credentials_path)
        self._config: dict = {}
        self._version: int = 0
        self._api_key: str = ""
        self._api_url: str = ""
        self._has_unpushed_changes: bool = False

    @property
    def version(self) -> int:
        return self._version

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def api_url(self) -> str:
        return self._api_url

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key) and bool(self._api_url)

    def set_credentials(self, api_key: str | None = None, api_url: str | None = None) -> None:
        """Override credentials from CLI args."""
        if api_key:
            self._api_key = api_key
            logger.info("Using API key from --api-key argument")
        if api_url:
            self._api_url = api_url
            logger.info("Using API URL from --api-url argument")
        self._warn_api_url()

    def load(self) -> None:
        """Load configuration: defaults -> hardware overrides -> local fallback -> env overrides."""
        # Load defaults
        if self._default_config_path.exists():
            with open(self._default_config_path) as f:
                self._config = json.load(f)
            logger.info("Loaded default config from %s", self._default_config_path)

        # Apply hardware-specific camera types from /etc/bugsi/hardware.conf
        self._apply_hardware_overrides()

        # Override with local config if it exists
        if self._local_config_path.exists():
            with open(self._local_config_path) as f:
                local = json.load(f)
            self._config = _deep_merge(self._config, local.get("config", local))
            self._version = local.get("version", self._version)
            logger.info("Loaded local config v%d from %s", self._version, self._local_config_path)

        # Load credentials
        self._load_credentials()

    def _apply_hardware_overrides(self) -> None:
        """Read /etc/bugsi/hardware.conf and apply camera type overrides."""
        hw_conf = Path(_HARDWARE_CONF_PATH)
        if not hw_conf.exists():
            logger.debug("No hardware config at %s, using defaults", _HARDWARE_CONF_PATH)
            return

        hw_config = ""
        try:
            for line in hw_conf.read_text().splitlines():
                line = line.strip()
                if line.startswith("HW_CONFIG="):
                    hw_config = line.split("=", 1)[1].strip()
                    break
        except OSError:
            logger.warning("Could not read %s", _HARDWARE_CONF_PATH)
            return

        if hw_config in _HW_CAMERA_OVERRIDES:
            overrides = _HW_CAMERA_OVERRIDES[hw_config]
            self._config = _deep_merge(self._config, overrides)
            logger.info(
                "Applied hardware config Option %s: still_camera=%s, event_camera=%s",
                hw_config,
                overrides["still_camera"]["type"],
                overrides["event_camera"]["type"],
            )
        elif hw_config:
            logger.warning("Unknown HW_CONFIG=%s in %s", hw_config, _HARDWARE_CONF_PATH)

    def _load_credentials(self) -> None:
        """Load API key and URL from credentials file or env vars."""
        # Env vars take priority (for dev/testing)
        env_key = os.environ.get("BUGSI_API_KEY", "")
        env_url = os.environ.get("BUGSI_API_URL", "")

        if env_key:
            self._api_key = env_key
            logger.info("Using API key from BUGSI_API_KEY env var")
        if env_url:
            self._api_url = env_url
            logger.info("Using API URL from BUGSI_API_URL env var")

        # If not set via env, read credentials file
        if not self._api_key or not self._api_url:
            if self._credentials_path.exists():
                with open(self._credentials_path) as f:
                    creds = json.load(f)
                if not self._api_key:
                    self._api_key = creds.get("api_key", "")
                if not self._api_url:
                    self._api_url = creds.get("api_url", "")
                logger.info("Loaded credentials from %s", self._credentials_path)
            else:
                logger.warning("Credentials file not found: %s", self._credentials_path)

        if not self._api_key:
            logger.warning(
                "No API key configured. Set BUGSI_API_KEY env var, use --api-key, or "
                "create %s with an 'api_key' field.", self._credentials_path,
            )
        if not self._api_url:
            logger.warning(
                "No API URL configured. Set BUGSI_API_URL env var, use --api-url, or "
                "create %s with an 'api_url' field.", self._credentials_path,
            )

        self._warn_api_url()

    def save_credentials(self, api_key: str | None = None, api_url: str | None = None) -> None:
        """Update credentials in memory and persist to credentials file."""
        if api_key is not None:
            self._api_key = api_key
        if api_url is not None:
            self._api_url = api_url

        # Read existing file to preserve fields not being changed
        creds: dict = {}
        if self._credentials_path.exists():
            try:
                with open(self._credentials_path) as f:
                    creds = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        creds["api_key"] = self._api_key
        creds["api_url"] = self._api_url

        self._credentials_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._credentials_path, "w") as f:
            json.dump(creds, f, indent=2)
        logger.info("Saved credentials to %s", self._credentials_path)
        self._warn_api_url()

    def _warn_api_url(self) -> None:
        if self._api_url and not self._api_url.rstrip("/").endswith("/device-data"):
            logger.warning(
                "API URL '%s' does not end with '/api/device-data'. "
                "Expected format: http://host:port/api/device-data",
                self._api_url,
            )

    def apply_remote(self, config: dict, version: int) -> bool:
        """Apply remote config from SaaS. Returns True if config changed."""
        if version <= self._version:
            return False

        self._config = _deep_merge(self._config, config)
        self._version = version
        self._persist_local()
        logger.info("Applied remote config v%d", version)
        return True

    @property
    def has_unpushed_changes(self) -> bool:
        return self._has_unpushed_changes

    def apply_local(self, config: dict) -> int:
        """Apply a local config change (from device webserver). Returns new version."""
        self._config = _deep_merge(self._config, config)
        self._version += 1
        self._has_unpushed_changes = True
        self._persist_local()
        logger.info("Applied local config change, now v%d", self._version)
        return self._version

    def clear_unpushed(self) -> None:
        """Mark local config as pushed to SaaS."""
        self._has_unpushed_changes = False

    def get(self, dotted_key: str, default=None):
        """Get a config value using dotted notation (e.g. 'upload.interval_minutes')."""
        keys = dotted_key.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def get_all(self) -> dict:
        """Return the full config dict."""
        return dict(self._config)

    def _persist_local(self) -> None:
        """Save current config to local file for offline use."""
        self._local_config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self._version, "config": self._config}
        with open(self._local_config_path, "w") as f:
            json.dump(payload, f, indent=2)
        logger.debug("Persisted config v%d to %s", self._version, self._local_config_path)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
