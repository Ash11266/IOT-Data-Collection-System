
import os
import time
from datetime import datetime, timezone

import psycopg
from pymodbus.client import ModbusTcpClient


MODBUS_HOST = os.getenv("MODBUS_HOST", "localhost")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
POLL_INTERVAL = float(os.getenv("MODBUS_POLL_INTERVAL", "1"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "iot_data"),
    "user": os.getenv("DB_USER", "iot_user"),
    "password": os.getenv("DB_PASSWORD", "iot_dev_password"),
}

DEVICE_ID = "solar-01"


def main():
    if POLL_INTERVAL <= 0:
        raise ValueError("MODBUS_POLL_INTERVAL must be greater than zero.")

    client = ModbusTcpClient(
        MODBUS_HOST,
        port=MODBUS_PORT,
        timeout=3,
    )

    last_sequence = None

    try:
        if not client.connect():
            raise ConnectionError(
                f"Could not connect to {MODBUS_HOST}:{MODBUS_PORT}"
            )

        print(f"Connected to Modbus server at {MODBUS_HOST}:{MODBUS_PORT}")
        print("Waiting for fresh dataset updates...")

        while True:
            try:
                result = client.read_holding_registers(
                    address=0,
                    count=5,
                    slave=1,
                )

                if result.isError():
                    print(f"Modbus read error: {result}")
                    time.sleep(POLL_INTERVAL)
                    continue

                registers = result.registers

                if len(registers) < 5:
                    print("Invalid response: expected five registers.")
                    time.sleep(POLL_INTERVAL)
                    continue

                voltage_raw, current_raw, power_raw, temp_raw, sequence = (
                    registers[:5]
                )

                # Sequence zero means no valid update has been published.
                if sequence == 0:
                    time.sleep(POLL_INTERVAL)
                    continue

                # Ignore the register state that existed when we started.
                # It may be stale data from a previous simulator run.
                if last_sequence is None:
                    last_sequence = sequence
                    print(
                        f"Ignoring initial register state "
                        f"(sequence={sequence}); waiting for a new update."
                    )
                    time.sleep(POLL_INTERVAL)
                    continue

                # Only insert when the simulator has updated the sequence.
                if sequence == last_sequence:
                    time.sleep(POLL_INTERVAL)
                    continue

                # Record the sequence only after a successful database insert.
                voltage = voltage_raw / 100
                current = current_raw / 1000
                power = power_raw / 100
                temperature = temp_raw / 100
                timestamp = datetime.now(timezone.utc)

                with psycopg.connect(**DB_CONFIG) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO telemetry (
                                device_id,
                                ts,
                                voltage_v,
                                current_a,
                                power_w,
                                temperature_c,
                                source_protocol
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, 'modbus')
                            """,
                            (
                                DEVICE_ID,
                                timestamp,
                                voltage,
                                current,
                                power,
                                temperature,
                            ),
                        )
                    conn.commit()

                last_sequence = sequence

                print(
                    f"Stored fresh Modbus reading "
                    f"(sequence={sequence}) | "
                    f"V={voltage:.2f} V | "
                    f"I={current:.3f} A | "
                    f"P={power:.2f} W | "
                    f"T={temperature:.2f} °C"
                )

            except (OSError, psycopg.Error) as exc:
                print(f"Collection error: {exc}")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nPoller interrupted.")

    finally:
        client.close()
        print("Modbus poller stopped.")


if __name__ == "__main__":
    main()
