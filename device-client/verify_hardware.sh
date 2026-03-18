#!/usr/bin/env bash
# =============================================================================
# BUGSI Hardware Verification Script
# Run after install_hardware.sh + reboot to check all components.
# =============================================================================

PASS="\033[1;32mPASS\033[0m"
FAIL="\033[1;31mFAIL\033[0m"
WARN="\033[1;33mWARN\033[0m"
results=()

check() {
    local name="$1" cmd="$2"
    echo "--- $name ---"
    if output=$(eval "$cmd" 2>&1); then
        echo "$output"
        echo -e "  [$PASS] $name"
        results+=("PASS: $name")
    else
        echo "$output"
        echo -e "  [$FAIL] $name"
        results+=("FAIL: $name")
    fi
    echo
}

echo "=== BUGSI Hardware Verification ==="
echo

# 1. Prophesee DKMS drivers
check "Prophesee DKMS drivers" \
    "dkms status 2>/dev/null | grep -q 'psee_sensor_drivers.*installed' && dkms status | grep psee_sensor_drivers"

# 2. Prophesee OpenEB
check "Prophesee OpenEB" \
    "ldconfig -p 2>/dev/null | grep -q metavision && echo 'OpenEB libraries found' || (test -f /usr/local/lib/libmetavision_sdk_core.so && echo 'OpenEB installed at /usr/local/lib')"

# 3. Prophesee dtoverlay
check "Prophesee dtoverlay (genx320,cam0)" \
    "grep -q 'dtoverlay=genx320,cam0' /boot/firmware/config.txt && echo 'dtoverlay=genx320,cam0 configured'"

# 4. ArduCam 64MP
check "ArduCam 64MP camera" \
    "rpicam-still --list-cameras 2>&1 | head -20"

# 5. ArduCam dtoverlay
check "ArduCam dtoverlay" \
    "grep -q 'dtoverlay=arducam-64mp' /boot/firmware/config.txt && echo 'dtoverlay=arducam-64mp configured'"

# 6. Witty Pi 5
check "Witty Pi 5 software" \
    "dpkg -l wp5 2>/dev/null | grep -q '^ii' && dpkg -l wp5 | grep wp5 | awk '{print \$2, \$3}'"

# 7. I2C enabled
check "I2C interface" \
    "ls /dev/i2c-* 2>/dev/null && echo 'I2C devices found' || (grep -q 'dtparam=i2c_arm=on' /boot/firmware/config.txt && echo 'I2C configured but /dev/i2c-* not found — reboot needed?')"

# 8. Zigbee coordinator serial port
check "Zigbee coordinator serial port" \
    "ls /dev/serial/by-id/*Sonoff*Zigbee* 2>/dev/null || ls /dev/serial/by-id/*10c4* 2>/dev/null || (test -c /dev/ttyUSB0 && echo '/dev/ttyUSB0')"

# 9. Zigbee database directory
check "Zigbee database (zigpy)" \
    "test -d /var/cache/bugsi && echo 'zigpy cache dir exists' && \
     (test -f /var/cache/bugsi/zigbee.db && echo 'zigpy database exists' || echo 'No database yet (will be created on first run)')"

# 10. LTE modem (usb0)
check "LTE modem (usb0)" \
    "ip addr show usb0 2>/dev/null | head -5"

# 11. Route metrics (wlan0 should have lower metric than usb0)
check "Network route metrics" \
    "ip route show default 2>/dev/null && \
     wlan_metric=\$(ip route show default dev wlan0 2>/dev/null | grep -oP 'metric \K[0-9]+' | head -1) && \
     usb_metric=\$(ip route show default dev usb0 2>/dev/null | grep -oP 'metric \K[0-9]+' | head -1) && \
     if [ -n \"\$wlan_metric\" ] && [ -n \"\$usb_metric\" ]; then \
         echo \"wlan0 metric=\$wlan_metric, usb0 metric=\$usb_metric\"; \
         [ \"\$wlan_metric\" -lt \"\$usb_metric\" ] || { echo 'WARNING: wlan0 should have lower metric than usb0'; false; }; \
     else \
         echo 'Could not determine both metrics (wlan0 or usb0 missing)'; \
     fi"

# 12. Network priority service
check "Network priority service" \
    "systemctl is-enabled bugsi-network-priority 2>/dev/null"

# Summary
echo "=== Summary ==="
for r in "${results[@]}"; do
    case "$r" in
        PASS*) echo -e "  [$PASS] ${r#PASS: }" ;;
        FAIL*) echo -e "  [$FAIL] ${r#FAIL: }" ;;
    esac
done

fail_count=$(printf '%s\n' "${results[@]}" | grep -c "^FAIL" || true)
pass_count=$(printf '%s\n' "${results[@]}" | grep -c "^PASS" || true)
echo
echo "$pass_count passed, $fail_count failed out of ${#results[@]} checks"
