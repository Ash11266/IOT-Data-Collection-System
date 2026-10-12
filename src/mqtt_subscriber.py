
import json
import os
from datetime import datetime, timezone

import psycopg
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = "apollo/solar-01/telemetry"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "iot_data"),
    "user": os.getenv("POSTGRES_USER", "iot_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "iot_dev_password"),
}

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"MQTT connection failed: {reason_code}")
        return

    print(f"Connected to MQTT broker at {BROKER}:{PORT}")
    client.subscribe(TOPIC, qos=1)
    print(f"Subscribed to {TOPIC}")

def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode("utf-8"))

        required = [
            "device_id", "ts", "voltage_v",
            "current_a", "power_w", "temperature_c"
        ]
        if not all(key in data for key in required):
            raise ValueError("Missing required telemetry fields")

        # Validate the timestamp and numeric measurements.
        ts = datetime.fromisoformat(data["ts"].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")

        measurements = [
            float(data[key])
            for key in [
                "voltage_v", "current_a",
                "power_w", "temperature_c"
            ]
        ]

        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry (
                        device_id, ts, voltage_v, current_a,
                        power_w, temperature_c, source_protocol
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'mqtt')
                    """,
                    (data["device_id"], ts, *measurements),
                )
            conn.commit()

        print(
            f"Stored MQTT reading: "
            f"V={measurements[0]:.2f}, "
            f"P={measurements[2]:.2f} W"
        )

    except (ValueError, TypeError, KeyError, psycopg.Error) as exc:
        print(f"Message rejected or database error: {exc}")

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="solar-mqtt-subscriber",
)

client.on_connect = on_connect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=30)

print(f"Connecting to {BROKER}:{PORT}...")
client.connect(BROKER, PORT, keepalive=60)
client.loop_forever()
