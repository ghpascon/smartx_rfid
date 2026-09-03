import logging
from smartx_rfid.webhook.xtrack import WebhookXtrack
import asyncio

logging.basicConfig(level=logging.DEBUG)


async def main():
    xtrack = WebhookXtrack(url="https://demo.smtx.com.br:6100/req", timeout=5, batch_time=1.0, queue_limit=5)
    tags = [
        {"device": "device1", "ant": "1", "epc": "100000000000000000000001"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000002"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000003"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000004"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000005"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000006"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000007"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000008"},
        {"device": "device1", "ant": "1", "epc": "100000000000000000000009"},
    ]
    for tag in tags:
        await xtrack.add_to_queue(tag)

    while True:
        await asyncio.sleep(1)  # Keep the program running to allow background tasks to complete


asyncio.run(main())
