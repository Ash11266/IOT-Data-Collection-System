# IoT Data Collection System

A Docker-based IoT telemetry pipeline that replays solar-panel photovoltaics (PV) data from a CSV dataset, publishes real-time readings over MQTT, exposes holding registers via Modbus TCP, and persists incoming telemetry from both protocols into PostgreSQL.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Dataset](#dataset)
- [Protocol Specifications](#protocol-specifications)
  - [MQTT Specification](#mqtt-specification)
  - [Modbus TCP Register Map](#modbus-tcp-register-map)
- [Database Schema](#database-schema)
- [Configuration Reference](#configuration-reference)
- [Quick Start (Docker Compose)](#quick-start-docker-compose)
- [Local Development Setup](#local-development-setup)
- [Verification and Testing](#verification-and-testing)
- [Troubleshooting and Design Considerations](#troubleshooting-and-design-considerations)
- [License](#license)

---

## Overview

This system demonstrates a dual-path IoT data ingestion architecture:

- **MQTT Pipeline (Push / Event-Driven):** The simulator serializes PV telemetry into JSON and publishes it to the Eclipse Mosquitto broker (`qos=1`). The MQTT subscriber consumes messages and inserts them into PostgreSQL.
- **Modbus TCP Pipeline (Pull / Polled):** The simulator scales telemetry into 16-bit integer holding registers on the Modbus server. A polling worker reads updated registers at a configured interval, decodes engineering units, and inserts them into PostgreSQL.
- **Unified Telemetry Storage:** Both pipelines write to a central PostgreSQL database table (`telemetry`), tracking device IDs, timestamps, electrical measurements, and the ingestion source (`mqtt` vs `modbus`).

---

## Architecture

```text
                        data/pv_dataset.csv
                                |
                                v
                      [ Telemetry Simulator ]
                         /             \
             JSON over  /               \  Scaled Registers
             MQTT:1883 /                 \  Modbus TCP:5020
                      v                   v
              [ Mosquitto Broker ]    [ Modbus Server ]
                      |                   |
               Push / Sub                 | Polled Read
                      v                   v
             [ MQTT Subscriber ]     [ Modbus Poller ]
                      \                   /
                       \                 /
                        v               v
                     [ PostgreSQL Database ]
                        (Table: telemetry)
```

---

## Technology Stack

- **Python 3.12** (Standard library `csv`, `datetime`, `json`)
- **Docker & Docker Compose** (Container orchestration & multi-container setup)
- **Eclipse Mosquitto 2.x** (MQTT broker)
- **Paho MQTT Python Client** (v2 API)
- **PyModbus 3.8.x** (Modbus TCP server and client)
- **PostgreSQL 16** (Relational time-series telemetry store)
- **psycopg 3** (PostgreSQL database adapter with explicit transaction management)

---

## Project Structure

```text
IOT-Data-Collection-System/
├── data/
│   └── pv_dataset.csv            # Solar panel telemetry dataset (CSV)
├── mosquitto/
│   └── mosquitto.conf            # Mosquitto broker configuration (anonymous access, port 1883)
├── sql/
│   └── init.sql                  # Database initialization script (table & index creation)
├── src/
│   ├── simulator.py              # CSV replay engine; publishes to MQTT & writes Modbus registers
│   ├── mqtt_subscriber.py        # Subscribes to MQTT topic and inserts readings into PostgreSQL
│   ├── modbus_server.py          # Async Modbus TCP holding-register server (port 5020)
│   ├── modbus_poller.py          # Periodic Modbus client; reads registers & inserts into PostgreSQL
│   └── mqtt_test_publisher.py    # Test utility to send a single sample payload via MQTT
├── .gitattributes
├── Dockerfile                    # Container image for Python microservices
├── docker-compose.yml            # Complete stack orchestration (Postgres, Mosquitto, microservices)
├── requirements.txt              # Python dependencies (paho-mqtt, psycopg, pymodbus)
└── README.md
```

---

## Dataset

The simulator replays solar PV data located at `data/pv_dataset.csv`.

### Required Columns

The simulator parses the CSV using Python's standard `csv.DictReader` and requires the following columns:

| Column Header | Description | Typical Unit |
|---|---|---|
| `voltage_v` | Panel output voltage | Volts (V) |
| `current_a` | Panel output current | Amperes (A) |
| `power_w` | Calculated/measured electrical power | Watts (W) |
| `panel_temperature_c` | PV panel surface temperature | Celsius (°C) |

*Note: Any additional columns in `pv_dataset.csv` (e.g., `light_lux`, `true_irradiance_wm2`, `fault`) are ignored by the simulator.*

---

## Protocol Specifications

### MQTT Specification

- **Broker Port:** `1883`
- **Topic:** `apollo/solar-01/telemetry`
- **QoS:** `1`
- **Payload Format:** JSON

```json
{
  "device_id": "solar-01",
  "ts": "2026-10-12T17:00:00.000000+00:00",
  "voltage_v": 6.24,
  "current_a": 0.112,
  "power_w": 0.69,
  "temperature_c": 22.50
}
```

### Modbus TCP Register Map

Modbus uses 16-bit unsigned holding registers (`uint16`, range `0`–`65535`). Floating-point engineering values are scaled by fixed factors:

- **Host Port:** `5020`
- **Slave / Unit ID:** `1`
- **Memory Area:** Holding Registers (`4xxxx`) starting at address `0`

| Address | Parameter | Datatype | Unit | Scaling Multiplier | Formula to Engineering Units |
|---|---|---|---|---|---|
| `0` | Voltage | `uint16` | Volts (V) | `× 100` | `Value = Register[0] / 100.0` |
| `1` | Current | `uint16` | Amperes (A) | `× 1000` | `Value = Register[1] / 1000.0` |
| `2` | Power | `uint16` | Watts (W) | `× 100` | `Value = Register[2] / 100.0` |
| `3` | Panel Temperature | `uint16` | °C | `× 100` | `Value = Register[3] / 100.0` |
| `4` | Sequence Counter | `uint16` | Counter | `× 1` | `(count % 65535) + 1` |

> **Sequence Counter Register (`Address 4`):**
> Because Modbus holding registers store state rather than discrete events, the simulator increments Register 4 with each new dataset row. The `modbus_poller.py` checks this register to detect when fresh data has arrived, preventing duplicate inserts while waiting between updates.

---

## Database Schema

Database initialization is managed by [`sql/init.sql`](sql/init.sql).

### Table: `telemetry`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | `PRIMARY KEY` | Unique autoincrementing record ID |
| `device_id` | `TEXT` | `NOT NULL` | Device identifier (e.g., `solar-01`) |
| `ts` | `TIMESTAMPTZ` | `NOT NULL` | Timestamp associated with measurement |
| `voltage_v` | `DOUBLE PRECISION` | | Voltage reading (V) |
| `current_a` | `DOUBLE PRECISION` | | Current reading (A) |
| `power_w` | `DOUBLE PRECISION` | | Power reading (W) |
| `temperature_c` | `DOUBLE PRECISION` | | Panel temperature (°C) |
| `source_protocol` | `TEXT` | `NOT NULL, CHECK (source_protocol IN ('mqtt', 'modbus'))` | Protocol used to collect this record |
| `received_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | Ingestion timestamp recorded by PostgreSQL |

An index `idx_telemetry_device_ts` is created on `(device_id, ts DESC)` to optimize time-series lookups.

---

## Configuration Reference

Environment variables configure each microservice:

| Variable | Target Component | Default Value | Description |
|---|---|---|---|
| `MQTT_HOST` | Simulator, Subscriber | `localhost` / `mosquitto` | Hostname or IP of MQTT broker |
| `MQTT_PORT` | Simulator, Subscriber | `1883` | Port of MQTT broker |
| `MODBUS_HOST` | Simulator, Poller | `localhost` / `modbus-server` | Hostname or IP of Modbus TCP server |
| `MODBUS_PORT` | Simulator, Poller | `5020` | Port of Modbus TCP server |
| `SIM_INTERVAL_SECONDS` | Simulator | `1` | Delay in seconds between replayed dataset rows |
| `MAX_ROWS` | Simulator | `0` | Maximum rows to replay (`0` = replay entire CSV) |
| `MODBUS_POLL_INTERVAL` | Poller | `1` | Delay in seconds between Modbus polling requests |
| `DB_HOST` | Subscriber, Poller | `localhost` / `postgres` | Hostname or IP of PostgreSQL database |
| `DB_PORT` | Subscriber, Poller | `5432` | Port of PostgreSQL database |
| `DB_NAME` / `POSTGRES_DB` | Subscriber, Poller | `iot_data` | Database name |
| `DB_USER` / `POSTGRES_USER` | Subscriber, Poller | `iot_user` | Database user |
| `DB_PASSWORD` / `POSTGRES_PASSWORD` | Subscriber, Poller | `iot_dev_password` | Database password |

> **Important Timing Note:**
> Set `MODBUS_POLL_INTERVAL` equal to or smaller than `SIM_INTERVAL_SECONDS` (e.g. `1` second). If the poller runs slower than the simulator (for instance, polling every 2 seconds when the simulator writes every 1 second), intermediate Modbus register values will be overwritten before they can be captured.

---

## Quick Start (Docker Compose)

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose support
- Git

### 2. Start the Stack

From the project root:

```powershell
docker compose up -d --build
```

### 3. Check Service Status

```powershell
docker compose ps
```

All 6 services should be running:
- `postgres` (healthy)
- `mosquitto`
- `modbus-server`
- `mqtt-subscriber`
- `modbus-poller`
- `simulator`

### 4. Monitor Service Logs

```powershell
# Follow logs for all services
docker compose logs -f

# Or follow a specific service
docker compose logs -f simulator
docker compose logs -f mqtt-subscriber
docker compose logs -f modbus-poller
```

### 5. Stop the Stack

```powershell
# Stop services and keep the database volume
docker compose down

# Stop services and delete the database volume (resets data)
docker compose down -v
```

---

## Local Development Setup

If you prefer to run or debug Python scripts directly on your host machine without containerizing the microservices:

### 1. Start Support Infrastructure

Run only PostgreSQL and Mosquitto via Docker:

```powershell
docker compose up -d postgres mosquitto
```

### 2. Set Up Python Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # Windows PowerShell
# or: source .venv/bin/activate # Linux / macOS

pip install -r requirements.txt
```

### 3. Run Microservices (Separate Terminals)

**Terminal 1 — Modbus TCP Server:**
```powershell
python src\modbus_server.py
```

**Terminal 2 — MQTT Subscriber:**
```powershell
python src\mqtt_subscriber.py
```

**Terminal 3 — Modbus Poller:**
```powershell
$env:MODBUS_POLL_INTERVAL = "1"
python src\modbus_poller.py
```

**Terminal 4 — Telemetry Simulator:**
```powershell
# Quick test: replay 10 rows
$env:MAX_ROWS = "10"
$env:SIM_INTERVAL_SECONDS = "1"
python src\simulator.py
```

---

## Verification and Testing

### 1. Verify Ingestion Counts by Protocol

Verify that records from both `mqtt` and `modbus` are persisted:

```powershell
docker compose exec postgres psql -U iot_user -d iot_data -c "SELECT source_protocol, COUNT(*) FROM telemetry GROUP BY source_protocol ORDER BY source_protocol;"
```

*Expected output (e.g. for a 10-row test run):*
```text
 source_protocol | count 
-----------------+-------
 modbus          |    10
 mqtt            |    10
(2 rows)
```

### 2. Inspect Recent Records

```powershell
docker compose exec postgres psql -U iot_user -d iot_data -c "SELECT id, device_id, ts, voltage_v, current_a, power_w, temperature_c, source_protocol FROM telemetry ORDER BY id DESC LIMIT 10;"
```

### 3. Test MQTT Subsystem Independently

To test the MQTT subscriber without running the full dataset simulator:

```powershell
python src\mqtt_test_publisher.py
```

### 4. Reset Telemetry Table

To clear all stored readings for a clean test run:

```powershell
docker compose exec postgres psql -U iot_user -d iot_data -c "TRUNCATE TABLE telemetry RESTART IDENTITY;"
```

---

## Troubleshooting and Design Considerations

### Push vs. Polling Characteristics
- **MQTT (Event-driven):** Every payload published to the broker triggers an `on_message` callback. Delivery is guaranteed as long as QoS and network connection hold.
- **Modbus TCP (State polling):** Modbus server holds the current state in registers. If the simulator writes faster than the poller samples (`SIM_INTERVAL_SECONDS < MODBUS_POLL_INTERVAL`), unpolled rows will be overwritten. Always align the polling frequency with the data generation rate.

### Transaction Management in psycopg 3
In `psycopg` (v3), connection context managers (`with psycopg.connect(...) as conn:`) open transactions that are rolled back on exit unless explicitly committed. Both `mqtt_subscriber.py` and `modbus_poller.py` issue an explicit `conn.commit()` after executing inserts.

### Port Conflicts
Ensure host ports are not occupied by other local services before starting Docker Compose:
- Port `1883`: Local Mosquitto or other MQTT brokers
- Port `5020`: Modbus TCP server
- Port `5432`: Local PostgreSQL instance

---

## License

This project is licensed under the [MIT License](LICENSE) (or specify your organization's license). Ensure compliance with the dataset's licensing terms before redistributing `data/pv_dataset.csv`.
