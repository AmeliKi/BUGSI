 bugsi upload --mock --api-key bugsi_taPcft7PGtPKo8bZAm4uqWwgmEQqRIDxhBvPSkELRLl3vsJc --api-url http://backend:8000/api/device-data

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

## Configuration

Configuration is managed remotely via the SaaS backend. The device polls for updates during each upload cycle. Default values in `config/default.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `telemetry.collection_interval_minutes` | 5 | How often to read sensors |
| `upload.interval_minutes` | 60 | How often to upload to backend |
| `upload.max_batch_size` | 100 | Max records per upload batch |
| `upload.battery_soc_threshold` | 20 | Skip upload below this SoC % |
| `power.night_mode_enabled` | true | Shut down at night |
| `power.night_start_hour` | 22 | Night mode start (UTC) |
| `power.night_end_hour` | 6 | Night mode end (UTC) |
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
