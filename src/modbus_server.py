
import asyncio

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

HOST = "0.0.0.0"
PORT = 5020
REGISTER_COUNT = 100


async def main():
    device = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * REGISTER_COUNT),
    )

    context = ModbusServerContext(slaves=device, single=True)

    print(f"Modbus TCP server listening on {HOST}:{PORT}", flush=True)

    await StartAsyncTcpServer(
        context=context,
        address=(HOST, PORT),
    )


if __name__ == "__main__":
    asyncio.run(main())
