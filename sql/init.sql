
CREATE TABLE IF NOT EXISTS telemetry (
    id BIGSERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    voltage_v DOUBLE PRECISION,
    current_a DOUBLE PRECISION,
    power_w DOUBLE PRECISION,
    temperature_c DOUBLE PRECISION,
    source_protocol TEXT NOT NULL
        CHECK (source_protocol IN ('mqtt', 'modbus')),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_ts
ON telemetry (device_id, ts DESC);
