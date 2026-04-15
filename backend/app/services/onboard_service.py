from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from app.exceptions import NotFoundError

_EXCLUDE_PATTERNS = {".venv", "__pycache__", ".pytest_cache", ".egg-info", ".git", "node_modules"}
# Heavy binary files that are downloaded on-demand via the /files/ endpoint
_EXCLUDE_EXTENSIONS = {".tgz", ".tar.gz", ".deb", ".whl"}


def generate_bootstrap_script(api_key: str, api_url: str, device_name: str) -> str:
    """Generate a self-contained bash script that onboards a Raspberry Pi device.

    The script runs all onboarding steps in sequence:
    1. Save credentials and download bundle
    2. Run hardware install (cameras, sensors, LTE, Zigbee, network)
    3. Install device-client daemon, start it, send first telemetry
    4. Install insect detector, start it
    """
    credentials = json.dumps({"api_key": api_key, "api_url": api_url}, indent=2)

    return f"""#!/usr/bin/env bash
set -euo pipefail

API_KEY="{api_key}"
API_URL="{api_url}"
DEVICE_NAME="{device_name}"

INSTALL_DIR="/opt/bugsi"
USB_DIR="/mnt/usb/bugsi"
BUNDLE_PATH="${{INSTALL_DIR}}/bugsi-bundle.tar.gz"

log()  {{ echo -e "\\033[1;32m[BUGSI]\\033[0m $*"; }}
warn() {{ echo -e "\\033[1;33m[WARN]\\033[0m $*"; }}
err()  {{ echo -e "\\033[1;31m[ERROR]\\033[0m $*" >&2; }}

# --- Root check ---
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root. Use: curl ... | sudo bash"
    exit 1
fi

echo
log "========================================="
log "  BUGSI Device Onboarding"
log "  Device: $DEVICE_NAME"
log "========================================="
echo

# ===========================================================================
# Step 1: Save credentials and download bundle
# ===========================================================================

log "--- Step 1/4: Connect to SaaS ---"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$USB_DIR"
mkdir -p "$USB_DIR/backup"

# Write credentials
log "Saving credentials to $USB_DIR/credentials.json ..."
cat > "$USB_DIR/credentials.json" <<'CREDEOF'
{credentials}
CREDEOF
chmod 600 "$USB_DIR/credentials.json"

# Download bundle
log "Downloading bundle ..."
curl -sfH "X-API-Key: $API_KEY" "$API_URL/onboard/bundle" -o "$BUNDLE_PATH"

# Extract bundle — contains device-client/ and insect-detector/ subdirectories
log "Extracting to $INSTALL_DIR ..."
tar xzf "$BUNDLE_PATH" -C "$INSTALL_DIR"
rm -f "$BUNDLE_PATH"

log "Step 1 complete: credentials saved, bundle downloaded."
echo

# ===========================================================================
# Step 2: Hardware install
# ===========================================================================

log "--- Step 2/4: Hardware Install ---"

CLIENT_DIR="${{INSTALL_DIR}}/device-client"

if [[ -f "$CLIENT_DIR/install_hardware.sh" ]]; then
    bash "$CLIENT_DIR/install_hardware.sh"
    log "Step 2 complete: hardware configured."
else
    warn "install_hardware.sh not found in bundle — skipping hardware install."
fi
echo

# ===========================================================================
# Step 3: Install device-client and send first telemetry
# ===========================================================================

log "--- Step 3/4: Install Device Client ---"

if [[ -f "$CLIENT_DIR/install.sh" ]]; then
    bash "$CLIENT_DIR/install.sh"
else
    err "device-client/install.sh not found in bundle!"
    exit 1
fi

# Start the daemon
log "Starting bugsi-daemon service ..."
systemctl start bugsi-daemon

# Send first telemetry (run as bugsi user to avoid root-owned files)
log "Collecting first telemetry reading ..."
sudo -u bugsi /opt/bugsi/venv/bin/bugsi telemetry

log "Uploading first telemetry to SaaS ..."
sudo -u bugsi /opt/bugsi/venv/bin/bugsi upload

log "Step 3 complete: device client running."
echo

# ===========================================================================
# Step 4: Install insect detector
# ===========================================================================

log "--- Step 4/4: Install Insect Detector ---"

DETECTOR_DIR="${{INSTALL_DIR}}/insect-detector"

if [[ -f "$DETECTOR_DIR/install.sh" ]]; then
    bash "$DETECTOR_DIR/install.sh"
    log "Starting bugsi-detector service ..."
    systemctl start bugsi-detector
    log "Step 4 complete: insect detector running."
else
    warn "insect-detector/install.sh not found in bundle — skipping detector install."
fi
echo

log "========================================="
log "  Onboarding complete!"
log "  Device: $DEVICE_NAME"
log "========================================="
echo
log "Useful commands:"
echo "  Daemon logs:    sudo journalctl -u bugsi-daemon -f"
echo "  Detector logs:  sudo journalctl -u bugsi-detector -f"
echo "  Status:         sudo systemctl status bugsi-daemon bugsi-detector"
echo "  Telemetry:      /opt/bugsi/venv/bin/bugsi telemetry"
echo
warn "A REBOOT is required for hardware dtoverlays to take effect."
echo "  sudo reboot"
echo
"""


def create_bundle_tarball(
    device_client_dir: str, insect_detector_dir: str | None = None
) -> bytes:
    """Create a tar.gz bundle containing device-client and optionally insect-detector.

    The tarball contains top-level directories (device-client/, insect-detector/)
    that extract directly into the install path.
    """
    src = Path(device_client_dir)
    if not src.is_dir():
        raise NotFoundError(f"Device client directory not found: {device_client_dir}")

    buf = io.BytesIO()

    def _filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(tarinfo.name).parts
        for part in parts:
            if any(part == pat or part.endswith(pat) for pat in _EXCLUDE_PATTERNS):
                return None
        if tarinfo.name.endswith(".pyc"):
            return None
        # Skip heavy binary files — devices download them via /files/ endpoint
        if any(tarinfo.name.endswith(ext) for ext in _EXCLUDE_EXTENSIONS):
            return None
        return tarinfo

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(src), arcname=src.name, filter=_filter)

        if insect_detector_dir:
            detector_src = Path(insect_detector_dir)
            if detector_src.is_dir():
                tar.add(str(detector_src), arcname=detector_src.name, filter=_filter)

    return buf.getvalue()
