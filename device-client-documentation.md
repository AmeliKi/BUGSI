# BUGSI Device Client - Functional Documentation

## Overview

The BUGSI Device Client is a daemon that runs on Raspberry Pi 5 devices deployed in the field for autonomous insect detection. It collects sensor data at configurable intervals, buffers it locally in SQLite, and periodically uploads to the BUGSI SaaS backend via LTE. The daemon is designed for low-power, offline-first operation with remote configuration management.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Scheduler                             │
│  ┌─────────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ Telemetry Loop  │ │ Upload Loop  │ │  Backup Loop    │  │
│  │ (every N min)   │ │ (every M min)│ │  (every K min)  │  │
│  └────────┬────────┘ └──────┬───────┘ └────────┬────────┘  │
│           │                 │                   │           │
│  ┌────────▼────────┐ ┌─────▼────────┐ ┌───────▼────────┐  │
│  │   Telemetry     │ │  Upload      │ │  Buffer        │  │
│  │   Collector     │ │  Cycle       │ │  Backup        │  │
│  └────────┬────────┘ └──────┬───────┘ └────────────────┘  │
│           │                 │                               │
│  ┌────────▼─────────────────▼──────────┐                   │
│  │         BufferStore (SQLite)         │                   │
│  └─────────────────────────────────────┘                   │
│                                                             │
│  ┌─────────────────────┐  ┌────────────────────────────┐   │
│  │   Power Manager     │  │   Config Manager            │   │
│  │   (mode transitions)│  │   (remote + local fallback) │   │
│  └─────────────────────┘  └────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │                           │
┌────────▼───────────────────────────▼──────────────────────┐
│               Hardware Abstraction Layer                    │
│  Battery │ Solar │ Climate │ LTE │ Storage │ System │ RTC  │
│  (mock or real implementations)                            │
└────────────────────────────────────────────────────────────┘
```

## Module Reference

### Hardware Abstraction (`bugsi_daemon/hardware/`)

#### Base Interfaces (`hardware/base.py`)

All hardware components implement abstract base classes, allowing seamless switching between real and mock implementations.

| Interface | Methods | Purpose |
|-----------|---------|---------|
| `HardwareSensor` | `initialize()`, `read()`, `shutdown()`, `is_healthy()` | Base sensor contract |
| `PowerControllable` | `power_on()`, `power_off()`, `is_powered()` | Hardware with power control |
| `LteModemInterface` | Extends `PowerControllable` + `wait_for_network()`, `get_signal_info()` | LTE modem operations |
| `PowerManagementInterface` | `get_rtc_time()`, `set_rtc_time()`, `schedule_shutdown()`, `schedule_wakeup()`, `get_next_wakeup()` | RTC and power scheduling |

#### Real Hardware Stubs (`hardware/*.py`)

Stub implementations for actual hardware. All methods raise `NotImplementedError` until real hardware drivers are implemented.

| Module | Hardware | Protocol |
|--------|----------|----------|
| `battery.py` | Victron SmartShunt | VE.Direct serial |
| `solar.py` | Victron SmartSolar MPPT | VE.Direct serial |
| `climate.py` | Zigbee SNZB-02WD | Zigbee via USB dongle |
| `lte.py` | Sixfab EG25-G | GPIO16 power, AT commands |
| `storage.py` | USB stick | Filesystem `statvfs` |
| `system.py` | Raspberry Pi 5 | `/sys/class/thermal`, `/proc/uptime` |
| `power_mgmt.py` | Witty Pi 4 Mini | I2C, RTC scheduling |

#### Mock Hardware (`hardware_mock/*.py`)

Realistic mock implementations for development and testing without real hardware. Activated via `--mock` CLI flag or `BUGSI_MOCK_HARDWARE=true` environment variable.

| Mock | Simulated Behavior |
|------|-------------------|
| `battery.py` | SoC drift simulation (24-28V, 20-100% SoC), realistic current/power/TTG values |
| `solar.py` | Time-of-day solar curve (peak at noon, zero at night), panel voltage/current |
| `climate.py` | Temperature 5-35 C with gradual drift, humidity 30-90% |
| `lte.py` | Power on/off state tracking, signal strength -60 to -110 dBm, returns `None` when powered off |
| `storage.py` | Configurable total/used MB, slowly increasing usage |
| `system.py` | CPU temperature 35-65 C, uptime via `time.monotonic()` |
| `power_mgmt.py` | Logs actions, stores wakeup/shutdown times, no-op operations |

### Configuration (`bugsi_daemon/config.py`)

#### ConfigManager

Manages device configuration with a layered priority system:

1. **Remote SaaS config** (highest priority) - polled during upload cycle
2. **Local fallback file** (`/mnt/usb/bugsi/config.json`) - persisted after each remote update
3. **Default config** (`config/default.json`) - shipped with the package

#### Config Structure

```json
{
  "telemetry": {
    "collection_interval_minutes": 5
  },
  "upload": {
    "interval_minutes": 60,
    "max_batch_size": 100,
    "battery_soc_threshold": 20
  },
  "power": {
    "night_mode_enabled": true,
    "night_start_hour": 22,
    "night_end_hour": 6,
    "modem_always_off": true,
    "zigbee_always_on": true
  },
  "storage": {
    "buffer_db_path": "/mnt/usb/bugsi/buffer.db",
    "backup_path": "/mnt/usb/bugsi/backup/",
    "backup_interval_minutes": 60,
    "cleanup_after_days": 30
  }
}
```

#### Key Methods

- `load()` - Loads defaults, then local fallback, then env overrides. Reads credentials.
- `apply_remote(config, version)` - Merges remote SaaS config using deep merge. Only applies if version is newer. Persists locally for offline use.
- `get(dotted_key, default)` - Access config values with dotted notation, e.g. `config.get("upload.interval_minutes", 60)`.
- `get_all()` - Returns the full config dictionary.

#### Credentials

Loaded from `/mnt/usb/bugsi/credentials.json` (written during device provisioning):

```json
{
  "api_key": "bugsi_your_device_key_here",
  "api_url": "https://your-server.example.com/api/device-data"
}
```

**Credential priority** (highest to lowest):
1. CLI arguments: `--api-key` / `--api-url`
2. Environment variables: `BUGSI_API_KEY` / `BUGSI_API_URL`
3. Credentials file on USB stick

**Missing credentials behavior:**
- `bugsi run`: Daemon stays alive and polls every 10 seconds for credentials to become available (env var set, credentials file created). Starts normally once found.
- Other commands (`telemetry`, `upload`, `status`): Exit immediately with an error message.

### SQLite Buffer (`bugsi_daemon/buffer/`)

#### BufferStore (`buffer/store.py`)

Local SQLite database for offline-first data buffering. All collected data is stored here until successfully uploaded and acknowledged by the backend.

**Database settings:**
- WAL journal mode (power-loss safe)
- NORMAL synchronous mode (performance + durability balance)

**Tables:**

| Table | Columns | Purpose |
|-------|---------|---------|
| `telemetry_buffer` | id, timestamp, payload_json, synced, synced_at, created_at | Sensor telemetry readings |
| `event_buffer` | id, timestamp, payload_json, synced, synced_at, created_at | Detection events |
| `thumbnail_buffer` | id, timestamp, file_path, local_event_id, synced, synced_at, created_at | Detection thumbnails |

All tables have an index on `synced` for efficient pending-record queries.

**Key Operations:**

| Method | Description |
|--------|-------------|
| `push_telemetry(reading)` | Insert a telemetry dict into the buffer |
| `push_event(event, thumbnail_path)` | Insert an event, optionally linking a thumbnail |
| `push_thumbnail(file_path, timestamp)` | Insert a thumbnail file reference |
| `get_pending_telemetry(limit)` | Get unsynced telemetry records (id, payload) |
| `get_pending_events(limit)` | Get unsynced event records |
| `get_pending_thumbnails(limit)` | Get unsynced thumbnail records (id, file_path, timestamp, event_id) |
| `mark_synced(table, ids)` | Mark records as successfully uploaded |
| `cleanup_old(days)` | Delete synced records older than N days |
| `get_stats()` | Return pending/total counts per table |

**Data persistence guarantee:** Records are only removed via `cleanup_old()`, which only deletes records that are both `synced = 1` AND older than the configured threshold (default 30 days). If upload fails, data accumulates locally and is retried on the next cycle.

#### BufferBackup (`buffer/backup.py`)

Periodic SQLite backup to USB stick for disaster recovery.

- Uses `VACUUM INTO` for a consistent, point-in-time backup
- Rotates old backups (keeps the most recent N, configurable)
- Backup path configurable via `storage.backup_path`
- Runs on its own schedule (default: every 60 minutes)

### Core Modules (`bugsi_daemon/core/`)

#### TelemetryCollector (`core/telemetry_collector.py`)

Reads all hardware sensors and composes a telemetry dict matching the backend `TelemetryReadingIn` schema.

**Telemetry fields produced:**

| Field | Source | Type |
|-------|--------|------|
| `timestamp` | UTC ISO 8601 | string |
| `battery_voltage` | Battery sensor | float |
| `battery_soc` | Battery sensor | float |
| `battery_current` | Battery sensor | float |
| `battery_power` | Battery sensor | float |
| `battery_consumed_ah` | Battery sensor | float |
| `battery_ttg_min` | Battery sensor | int |
| `temperature` | Climate sensor | float |
| `humidity` | Climate sensor | float |
| `lte_signal_strength` | LTE modem (last-known) | int |
| `lte_signal_quality` | LTE modem (last-known) | int |
| `storage_used_mb` | Storage sensor | int |
| `storage_total_mb` | Storage sensor | int |
| `cpu_temp` | System sensor | float |
| `uptime_seconds` | System sensor | int |

**Sensor failure handling:** Each sensor is read via `_safe_read()`, which catches exceptions and returns an empty dict. Missing fields become `None` in the telemetry payload (all fields are optional in the backend schema).

**LTE signal:** The modem is powered off between upload cycles. The collector stores the last-known LTE signal values and includes them in every telemetry reading. Values are updated during upload cycles when the modem is on, via `update_lte_signal()`.

#### UploadCycle (`core/upload_cycle.py`)

Manages a single upload cycle: power on LTE, upload buffered data, poll config, power off LTE.

**Upload cycle sequence:**

1. **Battery check** - Skip entire cycle if SoC is below `upload.battery_soc_threshold` (default 20%)
2. **Power on LTE** - Transition to `PowerMode.UPLOAD`
3. **Wait for network** - `lte.wait_for_network(timeout=60)`, abort if timeout
4. **Update LTE signal** - Read signal strength/quality while modem is on
5. **Upload telemetry** - Send pending telemetry in batches (max `upload.max_batch_size`), mark synced
6. **Upload events** - Send pending detection events, mark synced
7. **Upload thumbnails** - Send pending thumbnails one by one, mark synced
8. **Poll config** - Check for remote config updates, apply and acknowledge if new version
9. **Power off LTE** - Always runs in `finally` block, transitions back to `PowerMode.ACTIVE`

**Error handling:** Each step (telemetry upload, event upload, thumbnail upload, config poll) catches exceptions independently. A failure in one step does not prevent others from running. Unsent data remains in the buffer for the next cycle.

#### PowerManager (`core/power_manager.py`)

Orchestrates hardware power states to minimize energy consumption.

**Power Modes:**

| Mode | LTE Modem | Other Hardware | Trigger |
|------|-----------|----------------|---------|
| `ACTIVE` | Off | On | Default daytime operation |
| `UPLOAD` | On | On | During upload cycle |
| `NIGHT` | Off | Off (full shutdown) | Night hours via config |
| `LOW_BATTERY` | Off | Reduced | SoC below threshold |

**Mode transitions:**
- `ACTIVE -> UPLOAD`: Powers on LTE modem
- `UPLOAD -> ACTIVE`: Powers off LTE modem
- `* -> LOW_BATTERY`: Powers off LTE if on
- `* -> NIGHT`: Powers off LTE, initiates full shutdown

**Night mode detection:**
- Enabled via `power.night_mode_enabled` config (default: true)
- Active between `power.night_start_hour` (default: 22) and `power.night_end_hour` (default: 6) UTC
- Handles wrap-around correctly (e.g., 22:00 - 06:00 spans midnight)

**Shutdown sequence** (`prepare_shutdown()`):
1. Backup SQLite database
2. Power off LTE modem if on
3. Schedule wakeup at `power.night_end_hour` via Witty Pi RTC
4. Schedule system shutdown in 1 minute via Witty Pi
5. System powers off (~0.01W), RTC wakes at scheduled time
6. Daemon auto-starts via systemd on boot

#### Scheduler (`core/scheduler.py`)

Main asyncio event loop running three concurrent tasks:

| Task | Interval Config Key | Default | Description |
|------|-------------------|---------|-------------|
| Telemetry loop | `telemetry.collection_interval_minutes` | 5 min | Collect sensor data, check power conditions |
| Upload loop | `upload.interval_minutes` | 60 min | Run upload cycle, cleanup old records |
| Backup loop | `storage.backup_interval_minutes` | 60 min | Backup SQLite database |

**Power-aware scheduling:**
- Before each telemetry collection, checks if night mode should activate
- After each telemetry collection, checks for low battery and transitions to `LOW_BATTERY` mode if needed
- Config values are re-read each cycle, so remote config changes take effect immediately

**Graceful shutdown:**
- SIGTERM/SIGINT signals trigger `scheduler.shutdown()`
- Stops all loops, runs `power_manager.prepare_shutdown()`
- Ensures database backup before power off

### Network Client (`bugsi_daemon/net/`)

#### BugsiClient (`net/client.py`)

HTTP client for communicating with the BUGSI SaaS backend. Uses `httpx` with `X-API-Key` header authentication.

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `send_telemetry(readings)` | `POST /telemetry` | Upload telemetry readings in batch |
| `send_events(events)` | `POST /events` | Upload detection events in batch |
| `upload_thumbnail(image_data, timestamp)` | `POST /thumbnails` | Upload a detection thumbnail image |
| `poll_config()` | `GET /config` | Check for remote config updates |
| `ack_config(version)` | `POST /config/ack` | Acknowledge applied config version |
| `check_ota()` | `GET /ota/check` | Check for OTA firmware updates |
| `download_ota(deployment_id, dest)` | `GET /ota/{id}/download` | Download OTA package |
| `report_ota_status(deployment_id, status)` | `POST /ota/{id}/status` | Report OTA install status |
| `process_ota_update(deployment)` | - | Full OTA cycle (download, verify, extract, apply) |

All endpoints are relative to the base URL from credentials (`api_url`).

#### OtaInstaller (`net/ota_installer.py`)

Handles OTA firmware update installation:

1. **Verify checksum** - SHA-256 hash validation
2. **Extract and validate** - Unpack `tar.gz`, validate manifest, path traversal protection
3. **Apply** - Install to target directory
4. **Cleanup** - Remove staging files

### CLI (`bugsi_daemon/cli.py`)

Command-line interface for one-shot operations and daemon control.

| Command | Description |
|---------|-------------|
| `bugsi run` | Start the daemon (continuous operation) |
| `bugsi telemetry` | Collect and print one telemetry reading as JSON |
| `bugsi upload` | Run one upload cycle immediately |
| `bugsi status` | Show buffer stats, config version, power mode |
| `bugsi config` | Show current configuration |

**Global flags:**

| Flag | Env Var | Description |
|------|---------|-------------|
| `--mock` | `BUGSI_MOCK_HARDWARE=true` | Use mock hardware implementations |
| `--verbose` / `-v` | - | Enable debug logging |
| `--config-dir DIR` | - | Custom config directory |
| `--credentials FILE` | - | Custom credentials.json path |
| `--api-key KEY` | `BUGSI_API_KEY` | Device API key |
| `--api-url URL` | `BUGSI_API_URL` | Backend API URL |

All flags can be placed before or after the subcommand (e.g. both `bugsi --mock run` and `bugsi run --mock` work).

### Entry Point (`bugsi_daemon/main.py`)

Application entry point registered as the `bugsi` console script. Handles:

- Argument parsing (subcommands + global flags)
- Config loading (defaults + local fallback + env overrides + CLI args)
- Hardware selection (mock vs real based on `--mock` or env var)
- Credential waiting: if no API key/URL is configured, `bugsi run` polls every 10s until credentials appear
- Signal handlers (SIGTERM, SIGINT for graceful shutdown)
- Async event loop management

## Data Flow

### Telemetry Collection (every 5 minutes default)

```
Sensors → TelemetryCollector.collect() → BufferStore.push_telemetry() → SQLite
```

### Upload Cycle (every 60 minutes default)

```
PowerManager.set_mode(UPLOAD)    # LTE on
    ↓
LteModem.wait_for_network()
    ↓
BufferStore.get_pending_*()      # Read unsynced data
    ↓
BugsiClient.send_telemetry()     # HTTP POST to SaaS
BugsiClient.send_events()
BugsiClient.upload_thumbnail()
    ↓
BufferStore.mark_synced()         # Mark as uploaded
    ↓
BugsiClient.poll_config()        # Check for config updates
ConfigManager.apply_remote()     # Apply + persist locally
BugsiClient.ack_config()         # Acknowledge to SaaS
    ↓
PowerManager.set_mode(ACTIVE)    # LTE off
```

### Night Mode Shutdown

```
Scheduler detects night_start_hour
    ↓
BufferBackup.run_backup()        # Backup SQLite
    ↓
LteModem.power_off()             # LTE off
    ↓
PowerMgmt.schedule_wakeup()      # RTC alarm for morning
PowerMgmt.schedule_shutdown()    # Shutdown in 1 min
    ↓
System powers off (~0.01W)
    ↓
RTC wakes system at night_end_hour
    ↓
systemd starts bugsi-daemon      # Automatic restart
```

## Offline-First Design

The device client is designed to operate without network connectivity:

1. **All data buffered locally** - Telemetry, events, and thumbnails are stored in SQLite before any upload attempt
2. **Upload failures are non-destructive** - Data remains in the buffer until successfully synced
3. **Config persisted locally** - After first sync, config is saved to `/mnt/usb/bugsi/config.json` for offline use
4. **Cleanup only removes synced data** - `cleanup_old()` only deletes records that were successfully uploaded AND are older than the configured threshold
5. **Graceful degradation** - Missing sensors produce `None` fields, the daemon continues operating

## Deployment

### Raspberry Pi Installation

```bash
sudo ./install.sh
```

Creates:
- System user `bugsi`
- Python venv at `/opt/bugsi/venv/`
- Systemd service `bugsi-daemon`
- Directories: `/opt/bugsi/`, `/mnt/usb/bugsi/`, `/mnt/usb/bugsi/backup/`

### Docker (Development)

```bash
docker compose up -d device-client
```

Runs with `BUGSI_MOCK_HARDWARE=true` by default. Requires `TEST_DEVICE_API_KEY` in `.env`.

## Tests

85 tests covering all modules:

- **Hardware mock tests** - Correct field names and value ranges per sensor
- **Buffer tests** - SQLite CRUD, WAL mode, cleanup, backup/restore
- **Config tests** - Load defaults, apply remote, dotted-key access, local persistence
- **Power manager tests** - Mode transitions, night mode, low battery, shutdown
- **Telemetry collector tests** - Sensor reading, schema match, failure handling
- **Upload cycle tests** - HTTP mocking via `respx`, buffer state transitions, config poll
- **Scheduler tests** - Start/stop, telemetry collection timing
- **CLI tests** - Each command runs and produces expected output
- **Client tests** - HTTP client methods with `respx`

Run tests:
```bash
cd device-client
.venv/bin/pytest tests/ -v
```
