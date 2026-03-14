#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/bugsi"
VENV_DIR="${INSTALL_DIR}/detector-venv"
DETECTOR_DIR="${INSTALL_DIR}/insect-detector"
SERVICE_NAME="bugsi-detector"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== BUGSI Insect Detector Installer ==="
echo

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo ./install.sh)"
    exit 1
fi

# Create directories
echo "Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${DETECTOR_DIR}"

# Create separate venv (avoids dependency conflicts with device-client)
echo "Creating Python virtual environment..."
python3 -m venv "${VENV_DIR}"

# Install dependencies
echo "Installing detector dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install opencv-python-headless numpy

# Copy detector source
echo "Copying detector files..."
cp "${SCRIPT_DIR}/detector.py" "${DETECTOR_DIR}/"
mkdir -p "${DETECTOR_DIR}/config"
cp "${SCRIPT_DIR}/config/defaults.json" "${DETECTOR_DIR}/config/"

# Copy config defaults to shared config dir
echo "Copying default configuration..."
mkdir -p "${INSTALL_DIR}/config"
cp "${SCRIPT_DIR}/config/defaults.json" "${INSTALL_DIR}/config/detector_defaults.json"

# Install systemd service
echo "Installing systemd service..."
cp "${SCRIPT_DIR}/${SERVICE_NAME}.service" "/etc/systemd/system/"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

# Set permissions
chown -R bugsi:bugsi "${DETECTOR_DIR}"
chown -R bugsi:bugsi "${VENV_DIR}"

echo
echo "=== Insect Detector Installation complete ==="
echo
echo "Next steps:"
echo "  Start the detector:  sudo systemctl start ${SERVICE_NAME}"
echo "  View logs:           sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Check status:        sudo systemctl status ${SERVICE_NAME}"
echo "  Single capture test: ${VENV_DIR}/bin/python ${DETECTOR_DIR}/detector.py --single --mock -v"
