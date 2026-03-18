#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/bugsi"
VENV_DIR="${INSTALL_DIR}/venv"
USB_DIR="/mnt/usb/bugsi"
SERVICE_NAME="bugsi-daemon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRESH_VENV=false

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --fresh-venv) FRESH_VENV=true ;;
    esac
done

echo "=== BUGSI Device Client Installer ==="
echo

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo bash install.sh)"
    exit 1
fi

# Create system user
if ! id -u bugsi &>/dev/null; then
    echo "Creating system user 'bugsi'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin bugsi
fi

# Ensure bugsi user has access to camera and GPIO
for grp in video i2c gpio spi; do
    if getent group "$grp" >/dev/null 2>&1; then
        usermod -aG "$grp" bugsi 2>/dev/null || true
    fi
done

# Create directories
echo "Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${USB_DIR}"
mkdir -p "${USB_DIR}/backup"

# Create or reuse venv
if [[ "$FRESH_VENV" == true ]] || [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating Python virtual environment (fresh)..."
    python3 -m venv --clear --system-site-packages "${VENV_DIR}"
else
    echo "Reusing existing virtual environment (use --fresh-venv to rebuild)..."
fi

# Clean stale egg-info (may contain non-UTF-8 SOURCES.txt from previous builds)
rm -rf "${SCRIPT_DIR}"/*.egg-info

# Install package
echo "Installing bugsi-device-client..."
"${VENV_DIR}/bin/pip" install --no-cache-dir --upgrade pip
"${VENV_DIR}/bin/pip" install --no-cache-dir "${SCRIPT_DIR}"

# Copy config defaults
echo "Copying default configuration..."
mkdir -p "${INSTALL_DIR}/config"
cp "${SCRIPT_DIR}/config/default.json" "${INSTALL_DIR}/config/"

# Remove legacy service (renamed from bugsi-detector to bugsi-daemon)
if systemctl list-unit-files bugsi-detector.service &>/dev/null; then
    echo "Removing legacy bugsi-detector service..."
    systemctl stop bugsi-detector 2>/dev/null || true
    systemctl disable bugsi-detector 2>/dev/null || true
    rm -f /etc/systemd/system/bugsi-detector.service
fi

# Install systemd service
echo "Installing systemd service..."
cp "${SCRIPT_DIR}/${SERVICE_NAME}.service" "/etc/systemd/system/"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

# Set permissions
chown -R bugsi:bugsi "${INSTALL_DIR}"
chown -R bugsi:bugsi "${USB_DIR}"

echo
echo "=== Installation complete ==="
echo
echo "Next steps:"

# Check credentials
if [[ ! -f "${USB_DIR}/credentials.json" ]]; then
    echo "  WARNING: No credentials file found!"
    echo "  Create ${USB_DIR}/credentials.json with:"
    echo '  {"api_key": "bugsi_...", "api_url": "https://your-server/api/device-data"}'
    echo
fi

echo "  Start the daemon:  sudo systemctl start ${SERVICE_NAME}"
echo "  View logs:         sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Check status:      sudo systemctl status ${SERVICE_NAME}"
echo "  Test (mock mode):  ${VENV_DIR}/bin/bugsi telemetry --mock"
