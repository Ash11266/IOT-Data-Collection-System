
import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

# Dataset
CSV_PATH = Path("data/pv_dataset.csv")

# MQTT configuration
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "apollo/solar-01/telemetry"

# Modbus configuration
MODBUS_HOST = os.getenv("MODBUS_HOST", "localhost")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))

# Replay configuration
INTERVAL = float(os.getenv("SIM_INTERVAL_SECONDS", "1"))
MAX_ROWS = int(os.getenv("MAX_ROWS", "0"))  # 0 = all rows

DEVICE_ID = "solar-01"


def main():
    if INTERVAL < 0 or MAX_ROWS < 0:
        raise ValueError("INTERVAL and MAX_ROWS cannot be negative.")

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {CSV_PATH}")

    # Connect to MQTT broker
    mqtt_client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="solar-dataset-simulator",
    )
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    # Connect to Modbus server
    modbus_client = ModbusTcpClient(
        MODBUS_HOST,
        port=MODBUS_PORT,
        timeout=3,
    )

    try:
        if not modbus_client.connect():
            raise ConnectionError(
                f"Could not connect to Modbus at "
                f"{MODBUS_HOST}:{MODBUS_PORT}"
            )

        print(f"MQTT connected to {MQTT_HOST}:{MQTT_PORT}")
        print(f"Modbus connected to {MODBUS_HOST}:{MODBUS_PORT}")
        print(f"Replaying dataset: {CSV_PATH}")

        start_time = datetime.now(timezone.utc)
        count = 0

        with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            required = {
                "voltage_v",
                "current_a",
                "power_w",
                "panel_temperature_c",
            }
            missing = required - set(reader.fieldnames or [])

            if missing:
                raise ValueError(
                    f"Dataset is missing columns: {sorted(missing)}"
                )

            for row in reader:
                if MAX_ROWS and count >= MAX_ROWS:
                    break

                voltage = float(row["voltage_v"])
                current = float(row["current_a"])
                power = float(row["power_w"])
                temperature = float(row["panel_temperature_c"])

                # Use a generated UTC timestamp for this replay.
                timestamp = start_time + timedelta(
                    seconds=count * INTERVAL
                )
                ts = timestamp.isoformat()

                # 1. Publish the measurement through MQTT.
                payload = {
                    "device_id": DEVICE_ID,
                    "ts": ts,
                    "voltage_v": voltage,
                    "current_a": current,
                    "power_w": power,
                    "temperature_c": temperature,
                }

                info = mqtt_client.publish(
                    MQTT_TOPIC,
                    json.dumps(payload),
                    qos=1,
                )
                info.wait_for_publish(timeout=5)

                if not info.is_published():
                    raise RuntimeError("MQTT message was not published.")

                # 2. Update the Modbus holding registers.
                # Register scaling: V x100, A x1000,
                # W x100, temperature x100.
                # Sequence counter (1-based, wraps at 65535) lets the
                # Modbus poller detect each new update without duplicates.
                sequence = (count % 65535) + 1

                registers = [
                    round(voltage * 100),
                    round(current * 1000),
                    round(power * 100),
                    round(temperature * 100),
                    sequence,
                ]

                if any(value < 0 or value > 65535 for value in registers):
                    raise ValueError(
                        f"Measurement outside unsigned 16-bit range: "
                        f"{registers}"
                    )

                result = modbus_client.write_registers(
                    address=0,
                    values=registers,
                    slave=1,
                )

                if result.isError():
                    raise RuntimeError(
                        f"Modbus register write failed: {result}"
                    )

                count += 1

                if count % 10 == 0 or count == 1:
                    print(
                        f"Row {count}: "
                        f"V={voltage:.2f} V, "
                        f"I={current:.3f} A, "
                        f"P={power:.2f} W, "
                        f"T={temperature:.2f} °C "
                        f"| MQTT + Modbus OK"
                    )

                time.sleep(INTERVAL)

        print(f"Replay finished. Processed {count} rows.")

    finally:
        modbus_client.close()
        mqtt_client.disconnect()
        mqtt_client.loop_stop()


if __name__ == "__main__":
    main()
