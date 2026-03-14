#!/usr/bin/env bash
# Regression tests for install scripts — can run on any machine (not just RPi)
set -euo pipefail

PASS=0; FAIL=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

check() {
    local name="$1"; shift
    if "$@" 2>/dev/null; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

# 1. Syntax check
check "install.sh syntax valid" bash -n "$SCRIPT_DIR/install.sh"
check "install_hardware.sh syntax valid" bash -n "$SCRIPT_DIR/install_hardware.sh"

# 2. ArduCam section must NOT install libcamera_dev or libcamera_apps
# (replacing system libcamera breaks the Wayland desktop on RPi OS)
check "no libcamera_dev install" \
    bash -c "! grep -q '\-p libcamera_dev' '$SCRIPT_DIR/install_hardware.sh'"
check "no libcamera_apps install" \
    bash -c "! grep -q '\-p libcamera_apps' '$SCRIPT_DIR/install_hardware.sh'"

# 3. Network script must use 'ip route replace' (atomic) not 'ip route del' (destructive)
check "uses ip route replace" \
    bash -c "grep -q 'ip route replace' '$SCRIPT_DIR/install_hardware.sh'"
check "no ip route del default" \
    bash -c "! grep -q 'ip route del default via' '$SCRIPT_DIR/install_hardware.sh'"

# 4. Systemd default target is preserved
check "records systemd default target" \
    bash -c "grep -q 'systemctl get-default' '$SCRIPT_DIR/install_hardware.sh'"
check "restores systemd default target" \
    bash -c "grep -q 'systemctl set-default' '$SCRIPT_DIR/install_hardware.sh'"

# 5. config.txt backup mechanism exists
check "creates config.txt backup" \
    bash -c "grep -q 'bugsi-backup' '$SCRIPT_DIR/install_hardware.sh'"

# 6. Re-run safety: apt-get update must be inside DKMS guard (not top-level)
# Running apt-get update unconditionally on re-runs can pull kernel upgrades
# that break existing DKMS modules and dtoverlays, causing boot failure.
check "apt-get update inside DKMS guard" \
    bash -c "awk '/^if dkms status/,/^fi/ { if (/apt-get update/) found=1 } END { exit !found }' '$SCRIPT_DIR/install_hardware.sh'"

# 7. Filesystem health: pre-flight check and sync barriers exist
check "pre-flight filesystem health check" \
    bash -c "grep -q 'Checking filesystem health' '$SCRIPT_DIR/install_hardware.sh'"
check "sync_barrier function defined" \
    bash -c "grep -q 'sync_barrier()' '$SCRIPT_DIR/install_hardware.sh'"
check "sync barriers between stages" \
    bash -c "[ \$(grep -c 'sync_barrier' '$SCRIPT_DIR/install_hardware.sh') -ge 7 ]"
check "read-only mount detection" \
    bash -c "grep -q 'mounted read-only' '$SCRIPT_DIR/install_hardware.sh'"

# Summary
echo
echo "$PASS passed, $FAIL failed out of $(( PASS + FAIL )) checks"
[[ $FAIL -eq 0 ]]
