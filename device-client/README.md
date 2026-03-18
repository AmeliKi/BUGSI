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

# Fetch latest config from SaaS backend
.venv/bin/bugsi config-pull

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

### Local Web Server

The daemon includes a built-in web server (aiohttp) that starts automatically with `bugsi run`. There is no separate command to start it.

```bash
# Start the daemon (web server included)
export BUGSI_MOCK_HARDWARE=true
export BUGSI_API_KEY=test
export BUGSI_API_URL=http://localhost:8000/api/device-data
.venv/bin/bugsi run --mock --verbose
```

**Note:** Credentials (`BUGSI_API_KEY` / `BUGSI_API_URL`) are required — without them the daemon waits indefinitely and never starts the web server. For local development any dummy values work.

Once running, open `http://localhost:8080` in a browser (or `http://<device-ip>:8080` from another machine on the same network).

The web UI has four tabs:

- **Camera** — live MJPEG stream and snapshot
- **Gallery** — detection images (crops and frames)
- **Config** — view and edit device configuration (pushes changes to SaaS)
- **Status** — buffer stats, power mode, WLAN state

#### Verify the Web Server Is Running

Look for this log line in verbose output:

```
Web server started on 0.0.0.0:8080
```

Or from another terminal:

```bash
curl http://localhost:8080/api/status
```

#### Troubleshooting

If the web server doesn't start:

1. **No credentials** — without `BUGSI_API_KEY` / `BUGSI_API_URL` the daemon loops waiting for credentials and never reaches the web server. Set dummy values for local dev (see above)
2. **Night mode shuts down immediately** — the scheduler checks `power.night_mode_enabled` (default: `true`) with `awake_start_hour: 7` / `awake_end_hour: 21` (UTC). If the current UTC hour is outside this range, the daemon shuts down instantly. Fix: disable night mode in `config/default.json` (`"night_mode_enabled": false`) or adjust the awake hours
3. **Daemon not running** — the web server only runs inside `bugsi run`, not with other commands like `bugsi telemetry`
4. **`webserver.enabled` is `false`** — check with `bugsi config` and look for the `webserver` section
5. **Battery mode + RTC wake** — if `power.battery=true` and the device woke via RTC, WLAN stays off and the web server is skipped. On a cold boot with battery mode, WLAN auto-disables after `power.wlan_timeout_minutes` (default: 10 min) of inactivity
6. **Port conflict** — check with `lsof -i :8080`
7. **Backup path crash on macOS** — the default `storage.backup_path` is `/mnt/usb/bugsi/backup/` which doesn't exist on macOS. If the daemon crashes with `OSError: Read-only file system: '/mnt'`, set `"backup_path": "/tmp/bugsi_backup/"` in `config/default.json`

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/config` | Current configuration + version |
| `PUT` | `/api/config` | Update config (auto-pushes to SaaS) |
| `GET` | `/api/status` | Device status (buffer, power mode, WLAN) |
| `GET` | `/api/camera/snapshot` | Single JPEG snapshot |
| `GET` | `/api/camera/stream` | MJPEG live stream |
| `GET` | `/api/gallery` | List detections (`?limit=50&offset=0`) |
| `GET` | `/api/gallery/image/{subdir}/{filename}` | Serve detection image (crops/frames) |

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
docker compose exec device-client bugsi config-pull --mock
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

## Pairing a Zigbee Temperature & Humidity Sensor

The BUGSI device communicates directly with Zigbee sensors via [zigpy](https://github.com/zigpy/zigpy) + [bellows](https://github.com/zigpy/bellows) (no Node.js, no zigbee2mqtt, no MQTT broker). Any standard Zigbee temperature/humidity sensor should work, for example:

- SONOFF SNZB-02WD
- Tuya ZTH01 / ZTH02
- Aqara WSDCGQ11LM

The coordinator is a Sonoff Zigbee 3.0 USB Dongle Plus V2 (Silicon Labs EZSP).

### Pair via CLI

```bash
bugsi pair-zigbee
```

This powers on the USB dongle, starts the zigpy controller, opens a 120-second pairing window, and listens for new devices. Put your sensor into pairing mode (usually hold the button for 5 seconds) while the window is open.

Options:

```
--timeout SECONDS   Pairing window duration (default: 120)
--rename NAME       Rename the joined device to this friendly name
```

To pair and immediately set the friendly name used by the daemon:

```bash
bugsi pair-zigbee --rename climate_sensor
```

Example output:

```
Powering on Zigbee stack...
Zigbee stack ready. Opening pairing window for 120s...
Put your Zigbee sensor into pairing mode now.

  [JOINED] 0x00124b00abcdef01 (Tuya ZTH01) as "0x00124b00abcdef01"

Renaming "0x00124b00abcdef01" -> "climate_sensor"... OK

Paired devices:
  [ONLINE] climate_sensor (Tuya ZTH01, EndDevice)

Powering off Zigbee stack... Done.
```

After pairing, make sure the `zigbee.device_name` in your config matches the sensor's friendly name (default: `"climate_sensor"`). If you used `--rename climate_sensor`, no config change is needed.

### Test in mock mode

```bash
bugsi pair-zigbee --mock
```

## Checking Zigbee Sensor Connectivity

### Via CLI

```bash
bugsi test-hardware zigbee
```

This powers on the USB dongle, starts the zigpy controller, queries all paired devices, waits for sensor data, and powers everything off. Example output:

```
=== Zigbee Network ===
  Powering on Zigbee stack...
  Querying paired devices...
  Found 1 device(s):
    [ONLINE] climate_sensor (Tuya ZTH01, EndDevice, 0x00124b00abcdef01)
  Waiting 5s for sensor data from 'climate_sensor'...
  Sensor data: {'temperature': 22.3, 'humidity': 55.1, 'sensor_battery': 92, 'zigbee_linkquality': 150}
  OK
```

### Troubleshooting

If a sensor shows `OFFLINE` or no data arrives:

- **Check battery** — the sensor's coin cell may be depleted (check `sensor_battery` in telemetry)
- **Check range** — move the sensor closer to the ZBDongle-E USB stick
- **Re-pair the sensor**: `bugsi pair-zigbee --rename climate_sensor`
- **Check USB dongle is detected**: `lsusb | grep -i "cp21\|ch91\|silicon"`
- **Check serial port**: `ls /dev/serial/by-id/*Zigbee*`
- **Check zigpy database**: `ls -la /var/cache/bugsi/zigbee.db`
- **Check name mapping**: `cat /var/cache/bugsi/zigbee_names.json`

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
| `zigbee.serial_port` | "auto" | Zigbee coordinator serial port (or "auto") |
| `zigbee.adapter` | "ezsp" | Zigbee radio adapter type |
| `zigbee.device_name` | "climate_sensor" | Friendly name of the climate sensor |
| `zigbee.database_path` | /var/cache/bugsi/zigbee.db | zigpy network database |
| `zigbee.network_channel` | 11 | Zigbee network channel |
| `storage.buffer_db_path` | /mnt/usb/bugsi/buffer.db | SQLite database path |
| `storage.backup_path` | /mnt/usb/bugsi/backup/ | Backup directory |
| `storage.backup_interval_minutes` | 60 | How often to backup DB |
| `storage.cleanup_after_days` | 30 | Delete synced records after N days |
| `webserver.enabled` | true | Enable the local web server |
| `webserver.host` | "0.0.0.0" | Web server bind address |
| `webserver.port` | 8080 | Web server port |
| `webserver.camera_fps` | 2 | Live stream frames per second |
| `webserver.detections_dir` | /mnt/usb/bugsi/detections | Directory for detection images |

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
