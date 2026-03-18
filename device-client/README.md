# BUGSI Device Client

Daemon for Raspberry Pi insect detection devices. Collects sensor data, buffers locally in SQLite, and periodically uploads to the BUGSI SaaS backend via LTE.

## Local Development (Mock Hardware)

### Install

```bash
cd device-client
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### CLI Commands

All commands need credentials. For development, use environment variables:

```bash
export BUGSI_MOCK_HARDWARE=true
export BUGSI_API_KEY=your_device_api_key
export BUGSI_API_URL=http://localhost:8000/api/device-data
```

```bash
# Collect and print one telemetry reading
.venv/bin/bugsi telemetry

# Show current configuration
.venv/bin/bugsi config

# Show buffer statistics and power mode
.venv/bin/bugsi status

# Run one upload cycle (sends buffered data to backend)
.venv/bin/bugsi upload

# Start the daemon (runs continuously)
.venv/bin/bugsi run
```

Options:

```
--mock              Use mock hardware (or set BUGSI_MOCK_HARDWARE=true)
--verbose / -v      Enable debug logging
--config-dir DIR    Custom config directory
--credentials FILE  Custom credentials.json path
--api-key KEY       Device API key (overrides env var and credentials file)
--api-url URL       Backend API URL (overrides env var and credentials file)
```

Credentials can be provided via (highest to lowest priority):
1. CLI arguments: `--api-key` / `--api-url`
2. Environment variables: `BUGSI_API_KEY` / `BUGSI_API_URL`
3. Credentials file: `/mnt/usb/bugsi/credentials.json`

If no credentials are configured, `bugsi run` will stay alive and wait (polling every 10s) until credentials become available. Other commands will exit with an error.

### Run Tests

```bash
.venv/bin/pytest tests/ -v
```

## Docker

The device-client runs as a Docker service alongside the backend. It uses mock hardware by default.

### Start All Services

```bash
# From project root
docker compose up -d
```

This starts postgres, backend, frontend, and device-client. The device-client needs a device API key.

### Get a Device API Key

1. Start the backend: `docker compose up -d backend`
2. Create a device via the API (requires admin login first):

```bash
# Login as admin
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@bugsi.local","password":"YOUR_ADMIN_PASSWORD"}' \
  | jq -r '.access_token')

# Create a device
curl -s -X POST http://localhost:8000/api/devices \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"test-device","serial_number":"BUGSI-001"}' \
  | jq '.api_key'
```

3. Set the key in `.env`:

```bash
echo 'TEST_DEVICE_API_KEY=bugsi_...' >> .env
```

4. Restart the device-client:

```bash
docker compose up -d device-client
```

### Run Device Client Commands Inside Docker

```bash
# Open a shell in the device-client container
docker compose exec device-client bash

# Or run commands directly
docker compose exec device-client bugsi telemetry --mock
docker compose exec device-client bugsi status --mock
docker compose exec device-client bugsi config
docker compose exec device-client bugsi upload --mock
```

### View Logs

```bash
docker compose logs -f device-client
```

### Run Tests Inside Docker

```bash
docker compose exec device-client pytest tests/ -v
```

## Raspberry Pi Deployment

### Prerequisites

- Raspberry Pi with Python 3.12+
- USB stick mounted at `/mnt/usb/`

### Install

```bash
sudo ./install.sh
```

This creates a venv at `/opt/bugsi/`, installs the package, and sets up a systemd service.

### Credentials

Create `/mnt/usb/bugsi/credentials.json` on the USB stick:

```json
{
  "api_key": "bugsi_your_device_key_here",
  "api_url": "https://your-server.example.com/api/device-data"
}
```

### Manage the Service

```bash
sudo systemctl start bugsi-daemon
sudo systemctl stop bugsi-daemon
sudo systemctl status bugsi-daemon
sudo journalctl -u bugsi-daemon -f
```

## Testing on Real Hardware

The `test-hardware` command lets you test individual subsystems without running the full daemon.

### Available Subsystems

```bash
bugsi test-hardware cameras       # Still camera (Arducam) + event camera (Prophesee)
bugsi test-hardware climate       # Zigbee sensor power on → read → power off
bugsi test-hardware zigbee        # Full Zigbee network scan: list paired devices + read sensor data
bugsi test-hardware lte           # LTE modem power on → wait for network → signal info
bugsi test-hardware power         # Witty Pi RTC time, wakeup reason, temperature, voltage
bugsi test-hardware schedule      # Show computed active hours and night mode state
bugsi test-hardware sensors       # Storage, system, battery, solar readings
bugsi test-hardware capture       # Run one full image capture pipeline sequence
bugsi test-hardware all           # Run all of the above
```

Use `--mock` to test with mock hardware on a dev machine:

```bash
bugsi test-hardware all --mock
```

### Testing RTC Sleep/Wake Without Waiting for Sunrise

**Option 1: Fixed mode with a short window.** Set the awake window around the current time so the device schedules a shutdown soon:

```json
{
  "power": {
    "night_mode_type": "fixed",
    "awake_start_hour": 14,
    "awake_end_hour": 15
  }
}
```

**Option 2: Override wakeup directly via `wp5` CLI:**

```bash
# Schedule shutdown in 2 minutes, wakeup in 5 minutes
wp5 set shutdown_time "18 14:33:00"
wp5 set startup_time "18 14:35:00"
```

**Option 3: Sunrise/sunset with large offsets** to shift the active window to predictable times:

```json
{
  "power": {
    "night_mode_type": "sunrise_sunset",
    "location_lat": 48.2082,
    "location_lon": 16.3738,
    "sunrise_offset_minutes": -300,
    "sunset_offset_minutes": 300
  }
}
```

**Option 4: Just check the computed schedule** without triggering any sleep:

```bash
bugsi test-hardware schedule
```

### Step-by-Step Real Hardware Test

1. SSH into the Raspberry Pi and deploy the code
2. Test read-only sensors first (no side effects):
   ```bash
   bugsi test-hardware sensors
   bugsi test-hardware schedule
   ```
3. Test cameras (Prophesee on cam0, Arducam on cam1):
   ```bash
   bugsi test-hardware cameras
   ```
4. Test Zigbee connectivity (powers USB dongle on/off):
   ```bash
   bugsi test-hardware zigbee
   ```
5. Test LTE modem (powers modem on, waits for network):
   ```bash
   bugsi test-hardware lte
   ```
6. Test full capture pipeline (event detection → image → Zigbee → save):
   ```bash
   bugsi test-hardware capture
   ```
7. Test Witty Pi RTC:
   ```bash
   bugsi test-hardware power
   ```
8. Run the full daemon:
   ```bash
   bugsi run --verbose
   ```

## Checking Zigbee Sensor Connectivity

### Via CLI

```bash
bugsi test-hardware zigbee
```

This powers on the USB dongle and Zigbee2MQTT services, queries the bridge for all paired devices, waits for sensor data, and powers everything off. Example output:

```
=== Zigbee Network ===
  Powering on Zigbee stack...
  Querying paired devices...
  Found 1 device(s):
    [ONLINE] SNZB-02WD (SONOFF SNZB-02D, EndDevice, 0x00124b00abcdef01)
  Waiting 5s for sensor data from 'SNZB-02WD'...
  Sensor data: {'temperature': 22.3, 'humidity': 55.1}
  OK
```

### Manually via MQTT

On the Raspberry Pi, without the daemon:

```bash
# Start services
sudo systemctl start mosquitto
sudo systemctl start zigbee2mqtt

# List all paired devices (one-shot)
mosquitto_sub -t "zigbee2mqtt/bridge/devices" -C 1 | python3 -m json.tool

# Or request the device list explicitly
mosquitto_sub -t "zigbee2mqtt/bridge/response/devices" -C 1 &
mosquitto_pub -t "zigbee2mqtt/bridge/request/devices" -m ""

# Watch live sensor data from a specific device
mosquitto_sub -t "zigbee2mqtt/SNZB-02WD" -v
```

### Troubleshooting

If a sensor shows `OFFLINE` or no data arrives:

- **Check battery** in the SONOFF SNZB-02WD sensor
- **Check range** — move the sensor closer to the ZBDongle-E USB stick
- **Re-pair the sensor**: put Zigbee2MQTT in permit-join mode and reset the sensor (hold button for 5 seconds)
  ```bash
  mosquitto_pub -t "zigbee2mqtt/bridge/request/permit_join" -m '{"value": true, "time": 120}'
  ```
- **Check Zigbee2MQTT logs**: `sudo journalctl -u zigbee2mqtt -f`
- **Check USB dongle is detected**: `lsusb | grep -i "cp21\|ch91\|silicon"`

## Configuration

Configuration is managed remotely via the SaaS backend. The device polls for updates during each upload cycle. Default values in `config/default.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `telemetry.collection_interval_minutes` | 5 | How often to read sensors |
| `upload.interval_minutes` | 60 | How often to upload to backend |
| `upload.max_batch_size` | 100 | Max records per upload batch |
| `upload.battery_soc_threshold` | 20 | Skip upload below this SoC % |
| `upload.ota_check_enabled` | true | Check for OTA updates before uploading data |
| `power.night_mode_enabled` | true | Shut down at night |
| `power.night_mode_type` | "fixed" | "fixed" or "sunrise_sunset" |
| `power.awake_start_hour` | 7 | Fixed mode: device wakes at this hour |
| `power.awake_end_hour` | 21 | Fixed mode: device sleeps at this hour |
| `power.location_lat` | null | Sunrise/sunset mode: latitude |
| `power.location_lon` | null | Sunrise/sunset mode: longitude |
| `power.energy_saving` | false | Disable WLAN and unused hardware |
| `still_camera.type` | "arducam_64mp" | Still camera driver (registry name) |
| `event_camera.type` | "prophesee_genx320" | Event camera driver (registry name) |
| `image_capture.enabled` | true | Enable the image capture pipeline |
| `image_capture.cooldown_seconds` | 10 | Cooldown between detections |
| `image_capture.zigbee_warmup_seconds` | 5 | Wait for Zigbee data after power on |
| `zigbee.device_name` | "SNZB-02WD" | Zigbee2MQTT friendly name of the sensor |
| `storage.buffer_db_path` | /mnt/usb/bugsi/buffer.db | SQLite database path |
| `storage.backup_path` | /mnt/usb/bugsi/backup/ | Backup directory |
| `storage.backup_interval_minutes` | 60 | How often to backup DB |
| `storage.cleanup_after_days` | 30 | Delete synced records after N days |

## Architecture

```
Sensors (mock/real)     Buffer (SQLite)          Upload Cycle

Battery  ──┐
Solar    ──┤
Climate  ──┼── TelemetryCollector ──> buffer ──> LTE on
Storage  ──┤                                     ├─ send telemetry
System   ──┘                                     ├─ send events
                                                 ├─ send thumbnails
                                                 ├─ poll config
                                                 └─ LTE off
```

Data stays in the buffer until successfully uploaded. If upload is skipped (low battery, no network), data accumulates locally and retries on the next cycle.
