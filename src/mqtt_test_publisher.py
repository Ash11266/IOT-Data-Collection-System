
import json
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

TOPIC = "apollo/solar-01/telemetry"

payload = {
    "device_id": "solar-01",
    "ts": datetime.now(timezone.utc).isoformat(),
    "voltage_v": 18.5,
    "current_a": 1.2,
    "power_w": 22.2,
    "temperature_c": 35.4,
}

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="solar-test-publisher",
)

client.connect("localhost", 1883, keepalive=60)
client.loop_start()

try:
    info = client.publish(
        TOPIC,
        json.dumps(payload),
        qos=1,
    )
    info.wait_for_publish()
    print(f"Published test telemetry to {TOPIC}")
finally:
    client.disconnect()
    client.loop_stop()
