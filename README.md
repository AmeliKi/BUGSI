# BUGSI - Device Management SaaS

Backend and frontend for managing autonomous insect detection devices. Handles device registration, telemetry collection, remote configuration, and over-the-air (OTA) firmware updates.

## Deployment

### Prerequisites

- Docker and Docker Compose

### Setup

1. Copy the environment template and fill in required values:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Random string for JWT signing (e.g. `openssl rand -base64 32`) |
| `ADMIN_PASSWORD` | Initial admin password (min 8 characters) |
| `POSTGRES_PASSWORD` | Database password (default: `bugsi_dev`) |

Optional variables for OTA package building from git:

| Variable | Description |
|---|---|
| `GIT_REPO_URL` | Git repository URL for building OTA packages |
| `GIT_DEVICE_CODE_PATH` | Path to device code within the repo (default: `device-client/bugsi_daemon`) |

2. Start all services:

```bash
docker compose up -d
```

This starts four containers:

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16 database |
| `backend` | 8000 | FastAPI API server |
| `frontend` | 5173 | React dashboard |
| `device-client` | — | Device simulator CLI |

The backend automatically runs database migrations and creates the admin user on first start using the `ADMIN_EMAIL` (default: `admin@bugsi.local`) and `ADMIN_PASSWORD` from `.env`.

1. Verify the deployment:

```bash
curl http://localhost:8000/api/health
```

The frontend dashboard is available at `http://localhost:5173`.

### Rebuilding

After code changes, rebuild and restart the affected services:

```bash
# Rebuild all services
docker compose up -d --build

# Rebuild a single service (e.g. backend)
docker compose up -d --build backend
```

To do a clean rebuild (no cache):

```bash
docker compose build --no-cache
docker compose up -d
```

## API Keys & Device Registration

Devices authenticate with the backend using API keys sent via the `X-API-Key` header.

### Create a device

1. Log in as admin through the frontend, or obtain a token via the API:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@bugsi.local", "password": "YOUR_ADMIN_PASSWORD"}'
```

2. Create a device (requires the `access_token` from login):

```bash
curl -X POST http://localhost:8000/api/devices \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Field Unit 1", "serial_number": "BUGSI-001"}'
```

The response includes a plaintext `api_key` (format: `bugsi_...`). **Save it immediately** — it is only shown once.

### Regenerate a key

If a key is lost or compromised:

```bash
curl -X POST http://localhost:8000/api/devices/DEVICE_ID/regenerate-key \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

This invalidates the old key and returns a new one.

### Using the key from a device

All device-facing endpoints under `/api/device-data/` authenticate via the `X-API-Key` header:

```bash
curl http://localhost:8000/api/device-data/config \
  -H "X-API-Key: bugsi_YOUR_KEY_HERE"
```

## Device Onboarding

After creating a device (via the dashboard or API), you receive a one-time API key. Use it to onboard a Raspberry Pi with a single command:

```bash
curl -sfH "X-API-Key: bugsi_..." http://YOUR_SERVER:8000/api/device-data/onboard | sudo bash
```

This runs the full onboarding sequence automatically:

1. **Connect to SaaS** — saves credentials to `/mnt/usb/bugsi/credentials.json`
2. **Hardware install** — configures Prophesee event camera, ArduCam 64MP, Witty Pi 5, Zigbee2MQTT, LTE modem, and network priority
3. **Client install** — installs the `bugsi-daemon` systemd service, starts it, and sends the first telemetry reading

After onboarding completes, the device appears as "Online" in the dashboard. A reboot is required for hardware dtoverlays to take effect.

### Update device code

To pull the latest code from the SaaS and reinstall (without re-running hardware setup):

```bash
curl -sfH "X-API-Key: bugsi_..." http://YOUR_SERVER:8000/api/device-data/onboard/bundle \
  | sudo tar xzf - -C /opt/bugsi \
  && sudo bash /opt/bugsi/device-client/install.sh \
  && sudo systemctl restart bugsi-daemon bugsi-detector
```

To also rebuild the Python virtual environment from scratch (e.g. after dependency changes), add `--fresh-venv`:

```bash
curl -sfH "X-API-Key: bugsi_..." http://YOUR_SERVER:8000/api/device-data/onboard/bundle \
  | sudo tar xzf - -C /opt/bugsi \
  && sudo bash /opt/bugsi/device-client/install.sh --fresh-venv \
  && sudo systemctl restart bugsi-daemon bugsi-detector
```

### Manual steps (alternative)

If you prefer to run each onboarding step separately:

```bash
# Step 1: Download scripts and save credentials
curl -sfH "X-API-Key: bugsi_..." http://YOUR_SERVER:8000/api/device-data/onboard/bundle -o /tmp/bundle.tar.gz
sudo mkdir -p /opt/bugsi && sudo tar xzf /tmp/bundle.tar.gz -C /opt/bugsi

# Step 2: Hardware install
sudo bash /opt/bugsi/device-client/install_hardware.sh

# Step 3: Client install and first telemetry
sudo bash /opt/bugsi/device-client/install.sh
sudo systemctl start bugsi-daemon
/opt/bugsi/venv/bin/bugsi telemetry && /opt/bugsi/venv/bin/bugsi upload
```

## OTA Updates

### Upload a package

OTA packages are `.tar.gz` archives containing a `manifest.json` and the update files. Three package types are supported: `full`, `daemon_only`, `config_only`.

```bash
curl -X POST http://localhost:8000/api/ota/packages \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -F "file=@package.tar.gz" \
  -F "version=1.0.0" \
  -F "package_type=full" \
  -F "description=Initial release"
```

### Build a package from git

If `GIT_REPO_URL` is configured in `.env`, you can build packages directly from a git commit:

```bash
curl -X POST http://localhost:8000/api/ota/packages/build \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"commit_id": "abc123", "package_type": "full", "description": "Build from main"}'
```

### Deploy to devices

```bash
curl -X POST http://localhost:8000/api/ota/deploy \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"package_id": "PACKAGE_UUID", "device_ids": ["DEVICE_UUID_1", "DEVICE_UUID_2"]}'
```

### Device-side update flow

Devices poll for updates and report progress through these endpoints:

1. **Check** — `GET /api/device-data/ota/check` returns `has_update: true` with deployment details when an update is pending
2. **Download** — `GET /api/device-data/ota/{deployment_id}/download` returns the `.tar.gz` file
3. **Report status** — `POST /api/device-data/ota/{deployment_id}/status` with `{"status": "downloading|installing|completed|failed"}`

### Monitor deployments

```bash
curl http://localhost:8000/api/ota/deployments \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

Filter by device or status with query parameters: `?device_id=...&status=pending`.

## Device Local Webserver

Each device runs a local webserver (aiohttp on port 8080) that provides a web UI for field technicians to interact with the device directly over WLAN.

### Accessing the Webserver

1. Connect your phone/laptop to the **same WLAN network** as the Raspberry Pi
2. Find the Pi's IP address (shown on boot or via `hostname -I` on the Pi)
3. Open `http://<PI_IP>:8080` in a browser

The web UI has four tabs:

| Tab | Description |
|---|---|
| **Camera** | Live MJPEG stream and single snapshots from the device camera |
| **Gallery** | Browse stored detection images (crops and full frames) |
| **Config** | View and edit device configuration, push changes to SaaS |
| **Status** | Buffer stats, power mode, WLAN state |

### Configuration

The webserver is controlled via `config/default.json` (or remote config from SaaS):

```json
{
  "webserver": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "camera_fps": 2,
    "detections_dir": "/opt/bugsi/insect-detector/detections"
  }
}
```

| Setting | Default | Description |
|---|---|---|
| `webserver.enabled` | `true` | Enable/disable the local webserver |
| `webserver.host` | `0.0.0.0` | Bind address (`0.0.0.0` = all interfaces) |
| `webserver.port` | `8080` | HTTP port |
| `webserver.camera_fps` | `2` | MJPEG stream frame rate |
| `webserver.detections_dir` | `/opt/bugsi/insect-detector/detections` | Path to detection images |

### Config Editing and SaaS Sync

When you edit the config through the web UI and save:

1. The config is saved locally on the device immediately
2. The device attempts to push it to the SaaS backend (`PUT /api/device-data/config`)
3. If the push fails (e.g. no internet), it is retried on the next upload cycle

If the SaaS has a newer config version (e.g. admin changed it), the device push is rejected and the SaaS version takes priority on the next poll.

### Battery Mode (WLAN Power Saving)

For battery-powered field deployments, set `power.battery: true` in the config:

```json
{
  "power": {
    "battery": true,
    "wlan_timeout_minutes": 10
  }
}
```

Behavior:

| Boot Type | WLAN | Webserver |
|---|---|---|
| **Cold boot** (power on) | ON for 10 minutes | Available during WLAN window |
| **RTC wake** (Witty Pi scheduled) | OFF | Not started |

- Each HTTP request to the webserver resets the 10-minute inactivity timer
- After the timer expires with no interaction, WLAN is disabled to save power
- `wlan_timeout_minutes` is configurable (default: 10)

When `power.battery` is `false` (default), WLAN is always on and the webserver runs continuously.

### Logs

The webserver logs are part of the `bugsi-daemon` service output. View them with:

```bash
# Live logs on the Pi (via systemd)
journalctl -u bugsi-daemon -f

# Filter for webserver-related logs only
journalctl -u bugsi-daemon -f | grep "web\."

# Local development with verbose output
bugsi run --mock --verbose
```

The `--verbose` / `-v` flag enables DEBUG level logging, which includes every HTTP request, WLAN timer resets, config saves, and camera events.

## Device Client

See `device-client/README.md` for documentation on the device simulator and daemon.
