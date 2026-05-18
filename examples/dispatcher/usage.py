from smartx_rfid.dispatcher import EventDispatcher
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
)
dispatcher = EventDispatcher(
    dispatches_path="examples/dispatcher/dispatches",
    example_path="examples/dispatcher/dispatches_examples",
)


async def main():
    await dispatcher.add_async(
        "XPAD",
        "tag",
        {
            "epc": "000000000000000000000001",
            "tid": "e28000000000000000000001",
            "ant": 1,
            "rssi": -50,
        },
    )

    # await dispatcher.add_async(
    #     "XPAD",
    #     "tag",
    #     {
    #         "epc": "000000000000000000000002",
    #         "tid": "e28000000000000000000002",
    #         "ant": 3,
    #         "rssi": -50,
    #     },
    # )

    # await dispatcher.add_async(
    #     "R700",
    #     "tag",
    #     {
    #         "epc": "000000000000000000000003",
    #         "tid": "e28000000000000000000003",
    #         "ant": 2,
    #         "rssi": -50,
    #     },
    # )

    await dispatcher.stop()


asyncio.run(main())
