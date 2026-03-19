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

# --- Helpers ----------------------------------------------------------------

sync_barrier() {
    local stage="$1"
    sync
    if dmesg 2>/dev/null | tail -50 | grep -qi "ext4.*error"; then
        echo "ERROR: EXT4 errors detected after: $stage"
        echo "Run 'sudo fsck.ext4 -p <root-device>' from recovery."
        exit 1
    fi
    echo "Sync OK: $stage"
}

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
for grp in video i2c gpio spi dialout; do
    if getent group "$grp" >/dev/null 2>&1; then
        usermod -aG "$grp" bugsi 2>/dev/null || true
    fi
done

# Create directories
echo "Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${USB_DIR}"
mkdir -p "${USB_DIR}/backup"
mkdir -p /var/cache/bugsi

# Create or reuse venv
if [[ "$FRESH_VENV" == true ]] || [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating Python virtual environment (fresh)..."
    python3 -m venv --clear --system-site-packages "${VENV_DIR}"
else
    echo "Reusing existing virtual environment (use --fresh-venv to rebuild)..."
fi

# Clean stale egg-info (may contain non-UTF-8 SOURCES.txt from previous builds)
rm -rf "${SCRIPT_DIR}"/*.egg-info

# --- Route pip through tmpfs (SD card protection) ---------------------------
# Pip downloads, unpacks, and builds wheels in RAM.  Only the final install
# (copying into the venv) writes to the SD card.  Mirrors the apt tmpfs
# pattern in install_hardware.sh.
PIP_TMPDIR=$(mktemp -d /tmp/pip-build.XXXXX)
PIP_CACHE=$(mktemp -d /tmp/pip-cache.XXXXX)
trap "rm -rf ${PIP_TMPDIR} ${PIP_CACHE}" EXIT
export TMPDIR="$PIP_TMPDIR"

# --- Install packages (one-by-one with sync between each) ------------------
echo "Installing bugsi-device-client..."

# Upgrade pip
"${VENV_DIR}/bin/pip" install --cache-dir "$PIP_CACHE" --upgrade pip
sync_barrier "pip upgrade"

# Install deps one-by-one (auto-extracted from pyproject.toml).
# Each dep is followed by a sync barrier so that a corruption event
# only affects a single package rather than the whole venv.
echo "Installing dependencies one-by-one (SD card protection)..."
python3 -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('${SCRIPT_DIR}/pyproject.toml').read_text())
for dep in data['project']['dependencies']:
    print(dep)
" | while IFS= read -r dep; do
    echo "  Installing: $dep"
    "${VENV_DIR}/bin/pip" install --cache-dir "$PIP_CACHE" "$dep"
    sync_barrier "$dep"
done

# Install bugsi package itself (deps already satisfied)
"${VENV_DIR}/bin/pip" install --cache-dir "$PIP_CACHE" --no-deps "${SCRIPT_DIR}"
sync_barrier "bugsi package"

# --- Post-install verification ----------------------------------------------
# Scan all .so files for valid ELF headers.  Corrupted files are
# force-reinstalled automatically; persistent corruption aborts with
# fsck advice (likely SD card hardware failure).
echo "Verifying installed shared libraries..."
FAILED_SO=()
while IFS= read -r so_file; do
    if ! file "$so_file" | grep -q "ELF"; then
        FAILED_SO+=("$so_file")
    fi
done < <(find "${VENV_DIR}/lib" -name "*.so" -o -name "*.so.*" 2>/dev/null)

if [[ ${#FAILED_SO[@]} -gt 0 ]]; then
    echo "WARNING: ${#FAILED_SO[@]} corrupted .so file(s) — attempting repair..."
    REINSTALL_PKGS=()
    for f in "${FAILED_SO[@]}"; do
        pkg=$(echo "$f" | sed -n 's|.*/site-packages/\([^/]*\)/.*|\1|p' | tr '_' '-')
        [[ -n "$pkg" ]] && REINSTALL_PKGS+=("$pkg")
    done
    # Deduplicate
    REINSTALL_PKGS=($(printf '%s\n' "${REINSTALL_PKGS[@]}" | sort -u))
    for pkg in "${REINSTALL_PKGS[@]}"; do
        echo "  Force-reinstalling: $pkg"
        "${VENV_DIR}/bin/pip" install --cache-dir "$PIP_CACHE" --force-reinstall --no-deps "$pkg"
        sync
    done
    # Re-verify
    STILL_BAD=0
    for f in "${FAILED_SO[@]}"; do
        [[ -f "$f" ]] && ! file "$f" | grep -q "ELF" && STILL_BAD=$((STILL_BAD + 1))
    done
    if [[ $STILL_BAD -gt 0 ]]; then
        echo "ERROR: $STILL_BAD .so file(s) still corrupted. Likely SD card hardware failure."
        echo "Run: sudo fsck.ext4 -p <root-device>"
        exit 1
    fi
    echo "All .so files repaired."
else
    echo "All .so files OK."
fi
sync_barrier "post-install verification"

# Symlink bugsi CLI to system PATH
echo "Creating bugsi CLI symlink..."
ln -sf "${VENV_DIR}/bin/bugsi" /usr/local/bin/bugsi

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
chown -R bugsi:bugsi /var/cache/bugsi

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
echo "  Test (mock mode):  bugsi telemetry --mock"
echo "  Test hardware:     bugsi test-hardware all"
