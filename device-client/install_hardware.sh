#!/usr/bin/env bash
# =============================================================================
# BUGSI Hardware Install Script for Raspberry Pi 5 (Debian Trixie)
#
# Installs and configures:
#   1. Prophesee GenX320 Event Camera (cam0)
#   2. ArduCam 64MP Hawkeye (cam1)
#   3. Witty Pi 5 (Power Management + RTC)
#   4. Zigbee2MQTT (as systemd service)
#   5. LTE Modem (Quectel, ECM mode)
#   6. Network Priority (WLAN preferred over LTE)
#
# Usage: sudo ./install_hardware.sh
# =============================================================================
set -euo pipefail

CONFIG_TXT="/boot/firmware/config.txt"
PROPHESEE_DIR="/opt/prophesee"

# --- Helpers -----------------------------------------------------------------

log()  { echo -e "\033[1;32m[BUGSI]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()  { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

sync_barrier() {
    return
    local stage="$1"
    sync
    if dmesg 2>/dev/null | tail -50 | grep -qi "ext4.*error"; then
        err "EXT4 errors detected after stage: $stage"
        err "Aborting to prevent further filesystem damage."
        err "Run 'sudo fsck.ext4 -p <root-device>' from recovery mode."
        exit 1
    fi
    log "Sync complete after: $stage"
}

ensure_config_line() {
    local line="$1"

    # Check if already present (exact match, ignoring leading/trailing whitespace)
    if grep -qxF "$line" "$CONFIG_TXT" 2>/dev/null; then
        log "'$line' already in $CONFIG_TXT — skipped"
        return
    fi

    # Remove any duplicate/mangled versions of this line first
    local key="${line%%=*}"
    if [[ "$line" == *"="* ]]; then
        # For dtoverlay=X or dtparam=X, remove existing lines with same full value
        sed -i "/^${line//\//\\/}$/d" "$CONFIG_TXT" 2>/dev/null
    fi

    # Backup config.txt before first modification
    if [[ ! -f "${CONFIG_TXT}.bugsi-backup" ]]; then
        cp "$CONFIG_TXT" "${CONFIG_TXT}.bugsi-backup"
        log "Backed up $CONFIG_TXT to ${CONFIG_TXT}.bugsi-backup"
    fi

    # Insert under [all] section if it exists, otherwise append
    if grep -q '^\[all\]' "$CONFIG_TXT" 2>/dev/null; then
        # Find the line number of [all], then insert after it
        local all_line
        all_line=$(grep -n '^\[all\]' "$CONFIG_TXT" | tail -1 | cut -d: -f1)
        sed -i "${all_line}a\\${line}" "$CONFIG_TXT"
    else
        # Ensure file ends with newline, then append
        [[ -s "$CONFIG_TXT" ]] && [[ "$(tail -c1 "$CONFIG_TXT")" != "" ]] && echo >> "$CONFIG_TXT"
        echo "$line" >> "$CONFIG_TXT"
    fi
    log "Added '$line' to $CONFIG_TXT"
}

send_at_cmd() {
    local dev="$1" cmd="$2" wait="${3:-2}"
    # Configure serial port: 115200 baud, raw mode, 1s read timeout
    stty -F "$dev" 115200 raw -echo -echoe -echok cr0 2>/dev/null || true
    # Send command with timeout, discard response
    timeout 5 bash -c "echo -e '${cmd}\r' > '$dev'" 2>/dev/null || true
    sleep "$wait"
}

# --- Root check --------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo ./install_hardware.sh)"
    exit 1
fi

log "=== BUGSI Hardware Install Script ==="
log "Target: Raspberry Pi 5 — Debian Trixie"
echo

# --- Protect apt cache from SD card corruption ------------------------------
# Route apt downloads through tmpfs (RAM) so corrupted .deb files on the
# SD card can never break future installs.  Also clean any existing corrupt
# cache entries before we start.
log "Setting up tmpfs apt cache (SD card protection)..."
APT_TMPDIR=$(mktemp -d /tmp/apt-cache.XXXXX)
chmod 755 "$APT_TMPDIR"
APT_OPTS="-o Dir::Cache::Archives=${APT_TMPDIR}"
trap "rm -rf ${APT_TMPDIR}" EXIT
apt-get clean
log "apt cache redirected to ${APT_TMPDIR}"

# --- Filesystem health check ------------------------------------------------
log "Checking filesystem health..."
ROOT_DEV=$(findmnt -n -o SOURCE / 2>/dev/null || echo "")
# if dmesg 2>/dev/null | grep -qi "ext4.*error"; then
#     warn "Existing EXT4 errors detected in kernel log!"
#     warn "Run 'sudo fsck.ext4 -p $ROOT_DEV' from recovery/initramfs before proceeding."
#     warn "Continuing with filesystem errors risks further corruption."
#     read -r -p "[BUGSI] Continue anyway? (y/N) " confirm
#     [[ "$confirm" =~ ^[Yy]$ ]] || { err "Aborted — fix filesystem first."; exit 1; }
# fi
if mount | grep -q "on / .*ro[,)]"; then
    err "Root filesystem is mounted read-only — filesystem corruption likely."
    err "Boot into recovery and run: fsck.ext4 -p $ROOT_DEV"
    exit 1
fi

# --- Ensure WLAN preferred during install ------------------------------------
# Steps below need internet (git clone, wget, apt). If LTE (usb0) has a lower
# metric than WLAN but no connectivity, downloads will fail. Fix routing now;
# section 6 installs the persistent service for boot-time.
log "Setting network priority (WLAN > LTE) for install..."
for pair in "wlan0:100" "usb0:600"; do
    dev="${pair%%:*}"
    metric="${pair##*:}"
    if ! ip link show "$dev" &>/dev/null; then
        log "$dev: interface not found — skipping"
        continue
    fi
    route=$(ip route show dev "$dev" default 2>/dev/null | head -1)
    if [[ -z "$route" ]]; then
        log "$dev: no default route — skipping"
        continue
    fi
    gw=$(echo "$route" | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}')
    if [[ -z "$gw" ]]; then
        log "$dev: could not parse gateway — skipping"
        continue
    fi
    ip route replace default via "$gw" dev "$dev" metric "$metric" 2>/dev/null && \
        log "$dev: metric set to $metric" || warn "$dev: failed to set metric"
done

# --- Preserve boot target ---------------------------------------------------
# Record the current systemd default target before we install anything.
# Third-party install scripts (ArduCam, etc.) may change it as a side effect.
ORIGINAL_DEFAULT_TARGET=$(systemctl get-default 2>/dev/null || echo "")
log "Current systemd default target: ${ORIGINAL_DEFAULT_TARGET:-unknown}"

# =============================================================================
# 1. Prophesee GenX320 Event Camera (cam0)
# =============================================================================

log "--- [1/6] Prophesee GenX320 Event Camera ---"

# DKMS kernel drivers
if dkms status 2>/dev/null | grep -q "psee_sensor_drivers/1.0.1.*installed"; then
    log "Prophesee DKMS drivers already installed — skipping"
else
    # Install dependencies only when actually building (apt-get update on re-run
    # can pull in kernel upgrades that make existing DKMS modules incompatible)
    log "Installing Prophesee dependencies..."
    apt-get update -qq
    apt-get $APT_OPTS install -y "linux-headers-$(uname -r)" dkms
    apt-get $APT_OPTS install -y \
        build-essential cmake git wget curl \
        libboost-program-options-dev libboost-filesystem-dev libboost-system-dev libboost-thread-dev libboost-timer-dev \
        libopencv-dev \
        libusb-1.0-0-dev libprotobuf-dev protobuf-compiler \
        libglew-dev libglfw3-dev libgles2-mesa-dev \
        libhdf5-dev hdf5-tools pybind11-dev ffmpeg

    log "Cloning Prophesee RPi sensor drivers..."
    if [[ ! -d "${PROPHESEE_DIR}/rpi-sensor-drivers/.git" ]]; then
        mkdir -p "$PROPHESEE_DIR"
        git clone https://github.com/prophesee-ai/rpi-sensor-drivers.git "${PROPHESEE_DIR}/rpi-sensor-drivers"
    fi

    log "Building DKMS kernel drivers..."
    cd "${PROPHESEE_DIR}/rpi-sensor-drivers"
    make prepare
    if ! make all; then
        err "Prophesee driver build failed — skipping DKMS install to protect kernel"
        warn "Fix build errors above and re-run this script"
    else
        dkms add . 2>/dev/null || true
        if dkms build psee_sensor_drivers/1.0.1; then
            # Install without rebuilding initramfs (--force-modprobe avoids initramfs corruption)
            dkms install psee_sensor_drivers/1.0.1
            log "Prophesee DKMS drivers installed successfully"
        else
            err "DKMS build failed — skipping install to protect kernel"
            warn "Check build logs: dkms status"
        fi
    fi
fi

# OpenEB
if command -v metavision_viewer &>/dev/null || [[ -f /usr/local/lib/libmetavision_sdk_core.so ]]; then
    log "OpenEB already installed — skipping"
else
    log "Cloning and building OpenEB 5.1.1..."
    if [[ ! -d "${PROPHESEE_DIR}/openeb/.git" ]]; then
        git clone https://github.com/prophesee-ai/openeb.git --branch 5.1.1 --single-branch "${PROPHESEE_DIR}/openeb"
    fi

    cd "${PROPHESEE_DIR}/openeb"
    if ! git log --oneline -1 | grep -q "rpi"; then
        git apply "${PROPHESEE_DIR}/rpi-sensor-drivers/openeb-for-rpi.patch" || warn "Patch may already be applied"
    fi

    mkdir -p build && cd build
    cmake .. \
        -DUSE_OPENGL_ES3=ON \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_EXE_LINKER_FLAGS="-lGLESv2" \
        -DCMAKE_SHARED_LINKER_FLAGS="-lGLESv2"
    cmake --build . --config Release -- -j 4
    make install
    ldconfig

    # Verify Python bindings are importable (venv uses --system-site-packages)
    if python3 -c "from metavision_core.event_io import EventsIterator; print('OK')" 2>/dev/null; then
        log "OpenEB Python bindings verified"
    else
        warn "OpenEB Python bindings not importable from system Python"
        warn "The bugsi venv uses --system-site-packages, so ensure OpenEB's"
        warn "Python packages are installed for $(python3 --version 2>&1)"
    fi
fi

# Disable camera auto-detect (conflicts with manual overlays)
if grep -q '^camera_auto_detect=1' "$CONFIG_TXT" 2>/dev/null; then
    sed -i 's/^camera_auto_detect=1/camera_auto_detect=0/' "$CONFIG_TXT"
    log "Disabled camera_auto_detect in $CONFIG_TXT"
fi

# dtoverlay — only add if the overlay file was actually installed
if [[ -f /boot/firmware/overlays/genx320.dtbo ]]; then
    ensure_config_line "dtoverlay=genx320,cam0"
else
    warn "genx320.dtbo not found in /boot/firmware/overlays/ — skipping dtoverlay"
    warn "Re-run this script after DKMS build completes successfully"
fi

# Environment variables
if [[ ! -f /etc/profile.d/prophesee.sh ]]; then
    cat > /etc/profile.d/prophesee.sh <<'ENVEOF'
export PSEE_VAR_V4L2_BSIZE=1
export V4L2_HEAP=vidbuf_cached
# Suppress libcamera probe errors for the GenX320 (event cameras lack
# the mandatory V4L2 controls that libcamera's PISP handler expects).
export LIBCAMERA_LOG_LEVELS="*:WARN"
ENVEOF
    chmod 644 /etc/profile.d/prophesee.sh
    log "Created /etc/profile.d/prophesee.sh"
else
    log "/etc/profile.d/prophesee.sh already exists — skipped"
fi

sync_barrier "Prophesee GenX320"
echo

# =============================================================================
# 2. ArduCam 64MP Hawkeye (cam1)
# =============================================================================

log "--- [2/6] ArduCam 64MP Hawkeye ---"

ARDUCAM_IPA="/usr/share/libcamera/ipa/rpi/pisp/arducam_64mp.json"
if [[ -f /boot/firmware/overlays/arducam-64mp.dtbo ]] && grep -qE "^dtoverlay=arducam-64mp(,cam1)?$" "$CONFIG_TXT" 2>/dev/null && [[ -f "$ARDUCAM_IPA" ]]; then
    log "ArduCam 64MP already configured (driver + IPA) — skipping"
else
    log "Downloading ArduCam install script..."
    wget -qO /tmp/install_pivariety_pkgs.sh \
        https://github.com/ArduCAM/Arducam-Pivariety-V4L2-Driver/releases/download/install_script/install_pivariety_pkgs.sh
    chmod +x /tmp/install_pivariety_pkgs.sh

    # NOTE: We intentionally do NOT install libcamera_dev or libcamera_apps.
    # ArduCam's custom libcamera packages replace the system libcamera, which
    # breaks the Wayland compositor (labwc) on Raspberry Pi OS with Desktop.
    # On Debian Trixie, the system libcamera already supports arducam-64mp.

    log "Installing 64MP kernel driver..."
    /tmp/install_pivariety_pkgs.sh -p 64mp_pi_hawk_eye_kernel_driver

    log "Installing ArduCam libcamera IPA tuning file..."
    /tmp/install_pivariety_pkgs.sh -p libcamera

    # Explicit cam1 so libcamera's PISP handler only scans CSI port 1
    # (GenX320 is on cam0 and must not be enumerated by libcamera).
    # Clean up old entry without explicit port from earlier installs.
    sed -i '/^dtoverlay=arducam-64mp$/d' "$CONFIG_TXT" 2>/dev/null || true
    if [[ -f /boot/firmware/overlays/arducam-64mp.dtbo ]]; then
        ensure_config_line "dtoverlay=arducam-64mp,cam1"
    else
        warn "arducam-64mp.dtbo not found in /boot/firmware/overlays/ — skipping dtoverlay"
        warn "Re-run this script after ArduCam kernel driver installs successfully"
    fi
fi

sync_barrier "ArduCam 64MP"
echo

# =============================================================================
# 3. Witty Pi 5 (Power Management + RTC)
# =============================================================================

log "--- [3/6] Witty Pi 5 ---"

if dpkg -l wp5 2>/dev/null | grep -q "^ii"; then
    log "Witty Pi 5 software already installed — skipping"
else
    # Enable I2C
    log "Enabling I2C interface..."
    raspi-config nonint do_i2c 0 2>/dev/null || true
    ensure_config_line "dtparam=i2c_arm=on"

    log "Downloading Witty Pi 5 package..."
    if wget -qO /tmp/wp5_latest.deb https://www.uugear.com/repo/WittyPi5/wp5_latest.deb && [[ -s /tmp/wp5_latest.deb ]]; then
        log "Installing Witty Pi 5..."
        apt-get $APT_OPTS install -y /tmp/wp5_latest.deb
    else
        err "Failed to download Witty Pi 5 package — check network and URL"
        warn "URL: https://www.uugear.com/repo/WittyPi5/wp5_latest.deb"
    fi
fi

sync_barrier "Witty Pi 5"
echo

# =============================================================================
# 4. Zigbee (zigpy + bellows — no Node.js, no MQTT broker)
# =============================================================================

log "--- [4/6] Zigbee (zigpy + bellows) ---"

# --- uhubctl (USB hub power control for Zigbee dongle) ---
if ! command -v uhubctl &>/dev/null; then
    log "Installing uhubctl (USB hub power control)..."
    apt-get $APT_OPTS install -y uhubctl
fi

# --- zigpy + bellows are installed as Python deps via pyproject.toml ---
# Ensure the bugsi venv has them (in case of standalone pip install)
BUGSI_VENV="/opt/bugsi/venv"
if [[ -d "$BUGSI_VENV" ]]; then
    log "Ensuring zigpy + bellows are installed in bugsi venv..."
    "$BUGSI_VENV/bin/pip" install --quiet zigpy bellows
fi

# Ensure bugsi system user exists
if ! id bugsi &>/dev/null; then
    log "Creating bugsi system user..."
    useradd --system --create-home --shell /usr/sbin/nologin bugsi
fi

# Create zigpy database and name map directory
mkdir -p /var/cache/bugsi
chown bugsi:bugsi /var/cache/bugsi

# Add bugsi user to dialout group for serial port access
usermod -aG dialout bugsi 2>/dev/null || true

# Auto-detect serial port for informational purposes
ZIGBEE_PORT=""
for dev in /dev/serial/by-id/*Sonoff*Zigbee* /dev/serial/by-id/*10c4* /dev/ttyUSB0; do
    if [[ -e "$dev" ]]; then
        ZIGBEE_PORT="$dev"
        break
    fi
done
if [[ -n "$ZIGBEE_PORT" ]]; then
    log "Detected Zigbee coordinator at $ZIGBEE_PORT"
else
    log "No Zigbee coordinator detected (will auto-detect at runtime)"
fi

# --- Migration: remove old zigbee2mqtt + mosquitto if present ---
if systemctl is-enabled zigbee2mqtt &>/dev/null; then
    log "Removing old zigbee2mqtt service (replaced by zigpy)..."
    systemctl stop zigbee2mqtt 2>/dev/null || true
    systemctl disable zigbee2mqtt 2>/dev/null || true
    rm -f /etc/systemd/system/zigbee2mqtt.service
    systemctl daemon-reload
fi

if dpkg -l mosquitto 2>/dev/null | grep -q "^ii"; then
    log "Removing Mosquitto (no longer needed for Zigbee)..."
    systemctl stop mosquitto 2>/dev/null || true
    systemctl disable mosquitto 2>/dev/null || true
    apt-get $APT_OPTS remove -y mosquitto mosquitto-clients 2>/dev/null || true
fi

if [[ -d /opt/zigbee2mqtt ]]; then
    log "Old zigbee2mqtt directory found at /opt/zigbee2mqtt"
    warn "You can remove it manually: rm -rf /opt/zigbee2mqtt"
    warn "Note: existing Zigbee devices will need to be re-paired with zigpy"
fi

sync_barrier "Zigbee (zigpy)"
echo

# =============================================================================
# 5. LTE Modem (Quectel, ECM mode)
# =============================================================================

log "--- [5/6] LTE Modem (Quectel ECM) ---"

# Install minicom for AT command access
apt-get $APT_OPTS install -y minicom 2>/dev/null || true

# Disable ModemManager (conflicts with ECM)
if systemctl is-enabled ModemManager.service 2>/dev/null | grep -q "enabled"; then
    log "Disabling ModemManager (conflicts with ECM mode)..."
    systemctl stop ModemManager.service 2>/dev/null || true
    systemctl disable ModemManager.service 2>/dev/null || true
else
    log "ModemManager already disabled — OK"
fi

# Configure modem if present
MODEM_TTY=""
for dev in /dev/ttyUSB2 /dev/ttyUSB1 /dev/ttyUSB0; do
    if [[ -c "$dev" ]]; then
        MODEM_TTY="$dev"
        break
    fi
done

if [[ -n "$MODEM_TTY" ]]; then
    log "Found modem at $MODEM_TTY — configuring ECM mode..."

    # Set APN
    send_at_cmd "$MODEM_TTY" 'AT+CGDCONT=1,"IPV4V6","super"' 2

    # Enable ECM mode (usbnet=1) — always send, command is idempotent
    log "Setting modem to ECM mode (usbnet=1)..."
    send_at_cmd "$MODEM_TTY" 'AT+QCFG="usbnet",1' 2

    # Reboot modem to apply
    log "Rebooting modem..."
    send_at_cmd "$MODEM_TTY" 'AT+CFUN=1,1' 2
    log "Modem rebooting — wait ~30s for it to come back"
else
    warn "No Quectel modem detected (no /dev/ttyUSB* found) — skipping AT config"
    warn "Connect the modem and re-run this script, or configure manually"
fi

sync_barrier "LTE Modem"
echo

# =============================================================================
# 6. Network Priority (WLAN preferred over LTE)
# =============================================================================

log "--- [6/6] Network Priority (WLAN > LTE) ---"

METRIC_SCRIPT="/usr/local/bin/bugsi-network-priority.sh"

log "Creating network priority script..."
cat > "$METRIC_SCRIPT" <<'METRICEOF'
#!/bin/bash
# BUGSI Network Priority: prefer WLAN over LTE
# wlan0: metric 100 (preferred)
# usb0:  metric 600 (fallback LTE)
#
# Supports two modes:
#   - NetworkManager active: uses nmcli to set route-metric (persistent, NM-native)
#   - No NetworkManager: uses 'ip route replace' (atomic, no delete-then-add)

LOG_TAG="bugsi-net-priority"
log()  { echo "[${LOG_TAG}] $*"; logger -t "$LOG_TAG" "$*" 2>/dev/null || true; }

NM_ACTIVE=false
if systemctl is-active --quiet NetworkManager 2>/dev/null; then
    NM_ACTIVE=true
fi

# --- NetworkManager mode ---------------------------------------------------
set_metric_nm() {
    local dev="$1" metric="$2"

    # Find the NM connection that uses this device
    local conn_name
    conn_name=$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | grep ":${dev}$" | head -1 | cut -d: -f1)
    if [[ -z "$conn_name" ]]; then
        log "$dev: no active NetworkManager connection found, skipping"
        return 1
    fi

    if nmcli connection modify "$conn_name" ipv4.route-metric "$metric" 2>/dev/null; then
        log "$dev: set ipv4.route-metric=$metric on connection '$conn_name' via NetworkManager"
        # Use 'device reapply' to apply without full reconnect.
        # 'connection up' would trigger a reconnect cycle and re-fire the NM dispatcher.
        nmcli device reapply "$dev" 2>/dev/null || true
        return 0
    else
        log "$dev: failed to set route-metric via nmcli"
        return 1
    fi
}

# --- ip route mode (no NetworkManager) ------------------------------------
set_metric_iproute() {
    local dev="$1" metric="$2"
    local route gw src

    route=$(ip route show dev "$dev" default 2>/dev/null | head -1)
    if [[ -z "$route" ]]; then
        log "$dev: no default route found, skipping"
        return 1
    fi

    gw=$(echo "$route" | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}')
    src=$(echo "$route" | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')

    if [[ -z "$gw" ]]; then
        log "$dev: could not parse gateway from route '$route', skipping"
        return 1
    fi

    # Use 'ip route replace' — atomic (adds or replaces in one operation).
    # Unlike delete-then-add, it never leaves the device without a route.
    local cmd="ip route replace default via $gw dev $dev metric $metric"
    [[ -n "$src" ]] && cmd="$cmd src $src"

    if eval "$cmd" 2>/dev/null; then
        log "$dev: route replaced — metric $metric (via $gw${src:+ src $src})"

        # Clean up old route without our metric (if any remain)
        ip route show dev "$dev" default 2>/dev/null | grep -v "metric $metric" | while IFS= read -r old; do
            ip route del $old 2>/dev/null || true
        done
        return 0
    else
        log "$dev: 'ip route replace' FAILED — route left unchanged"
        return 1
    fi
}

# --- Wait for interface to have a default route ----------------------------
wait_for_route() {
    local dev="$1" max_wait="${2:-60}" interval=5
    local waited=0

    while (( waited < max_wait )); do
        if ip route show dev "$dev" default 2>/dev/null | grep -q "via"; then
            return 0
        fi
        if [[ "$NM_ACTIVE" == true ]]; then
            if nmcli -t -f DEVICE connection show --active 2>/dev/null | grep -q "^${dev}$"; then
                return 0
            fi
        fi
        log "$dev: waiting for default route... (${waited}s / ${max_wait}s)"
        sleep "$interval"
        (( waited += interval ))
    done

    log "$dev: no default route after ${max_wait}s"
    return 1
}

# --- Check if metrics are already correct -----------------------------------
check_metric() {
    local dev="$1" metric="$2"
    ip route show dev "$dev" default 2>/dev/null | grep -q "metric $metric"
}

# --- Main -------------------------------------------------------------------
log "Starting network priority configuration (NM_ACTIVE=$NM_ACTIVE)"

for pair in "wlan0:100" "usb0:600"; do
    dev="${pair%%:*}"
    metric="${pair##*:}"

    # Skip if metric is already set correctly (avoids unnecessary reconnect churn)
    if check_metric "$dev" "$metric"; then
        log "$dev: metric already $metric — nothing to do"
        continue
    fi

    if ! wait_for_route "$dev" 60; then
        log "$dev: skipping metric set — no route available"
        continue
    fi

    if [[ "$NM_ACTIVE" == true ]]; then
        set_metric_nm "$dev" "$metric" || set_metric_iproute "$dev" "$metric" || true
    else
        set_metric_iproute "$dev" "$metric" || true
    fi
done

log "Network priority configuration complete"
ip route show default 2>/dev/null | while read -r line; do log "  $line"; done
METRICEOF
chmod +x "$METRIC_SCRIPT"

# Systemd service to apply on boot (always ensure it exists and is enabled)
if ! systemctl is-enabled bugsi-network-priority &>/dev/null; then
    log "Creating network priority systemd service..."
    cat > /etc/systemd/system/bugsi-network-priority.service <<NETSVCEOF
[Unit]
Description=BUGSI Network Priority (WLAN > LTE)
After=network-online.target NetworkManager-wait-online.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 5
ExecStart=$METRIC_SCRIPT
RemainAfterExit=yes
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
NETSVCEOF

    systemctl daemon-reload
    systemctl enable bugsi-network-priority.service
fi

# NetworkManager dispatcher to re-apply when interfaces change
DISPATCHER_DIR="/etc/NetworkManager/dispatcher.d"
if [[ -d "$DISPATCHER_DIR" ]]; then
    log "Creating NetworkManager dispatcher hook..."
    cat > "${DISPATCHER_DIR}/99-bugsi-metric" <<'DISPEOF'
#!/bin/bash
# Re-apply BUGSI network metrics when wlan0 or usb0 come up
IFACE="$1"
ACTION="$2"
LOCK="/tmp/bugsi-net-priority.lock"

if [[ "$ACTION" != "up" ]] || [[ "$IFACE" != "wlan0" && "$IFACE" != "usb0" ]]; then
    exit 0
fi

# Skip if already running (prevents reconnect loops)
if [[ -f "$LOCK" ]]; then
    exit 0
fi

touch "$LOCK"
/usr/local/bin/bugsi-network-priority.sh &>/dev/null || true
rm -f "$LOCK"
DISPEOF
    chmod +x "${DISPATCHER_DIR}/99-bugsi-metric"
fi

sync_barrier "Network Priority"
echo

# =============================================================================
# Done
# =============================================================================

# --- Validate config.txt ----------------------------------------------------
if [[ -f "$CONFIG_TXT" ]]; then
    if [[ ! -s "$CONFIG_TXT" ]]; then
        err "config.txt is EMPTY — restoring from backup"
        if [[ -f "${CONFIG_TXT}.bugsi-backup" ]]; then
            cp "${CONFIG_TXT}.bugsi-backup" "$CONFIG_TXT"
            log "Restored config.txt from backup"
        else
            err "No backup found at ${CONFIG_TXT}.bugsi-backup — manual intervention required"
        fi
    fi
else
    err "config.txt does not exist — restoring from backup"
    if [[ -f "${CONFIG_TXT}.bugsi-backup" ]]; then
        cp "${CONFIG_TXT}.bugsi-backup" "$CONFIG_TXT"
        log "Restored config.txt from backup"
    fi
fi

# --- Restore boot target if changed by any install step ---------------------
if [[ -n "$ORIGINAL_DEFAULT_TARGET" ]]; then
    CURRENT_TARGET=$(systemctl get-default 2>/dev/null || echo "")
    if [[ "$CURRENT_TARGET" != "$ORIGINAL_DEFAULT_TARGET" ]]; then
        warn "Systemd default target changed from '$ORIGINAL_DEFAULT_TARGET' to '$CURRENT_TARGET'"
        log "Restoring original default target: $ORIGINAL_DEFAULT_TARGET"
        systemctl set-default "$ORIGINAL_DEFAULT_TARGET"
    else
        log "Systemd default target unchanged: $CURRENT_TARGET — OK"
    fi
fi

log "=== Hardware installation complete ==="
echo
log "config.txt entries:"
grep -E "^(dtoverlay=genx320|dtoverlay=arducam-64mp|dtparam=i2c_arm)" "$CONFIG_TXT" | while read -r line; do
    echo "  $line"
done
echo
log "Services enabled:"
for svc in bugsi-network-priority; do
    status=$(systemctl is-enabled "$svc" 2>/dev/null || echo "not found")
    echo "  $svc: $status"
done
echo
warn "A REBOOT is required for dtoverlays and kernel modules to take effect."
echo "  sudo reboot"
echo
log "After reboot, verify with:"
echo "  dkms status                    # Prophesee drivers"
echo "  rpicam-still --list-cameras    # ArduCam 64MP"
echo "  wp5                            # Witty Pi 5"
echo "  ls /dev/serial/by-id/*Zigbee*   # Zigbee coordinator"
echo "  ls /var/cache/bugsi/           # zigpy database"
echo "  ip addr show usb0             # LTE interface"
echo "  ip route                       # Route metrics"
echo
log "SD card health:"
echo "  sudo dmesg | grep -i 'ext4\|mmc\|error'   # Filesystem/MMC errors"
echo "  sudo fsck.ext4 -n /dev/mmcblk0p2           # Dry-run filesystem check"
