import asyncio
import logging

from smartx_rfid.dispatcher import EventDispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    dispatcher = EventDispatcher(
        dispatches_path="examples/dispatcher/dispatches",
        example_path="examples/dispatcher/dispatches_examples",
        max_workers=8,
        max_queue_size=50_000,
    )

    # 1) Create a new POST dispatch JSON
    post_dispatch = {
        "dispatch_type": "post",
        "on_event": "connection",
        "url": "http://localhost:5001/device/connection",
        "retry_attempts": 3,
        "retry_backoff_seconds": 0.2,
        "filters": [
            {
                "key": "{name}",
                "value": "XPAD",
                "operator": "eq",
            }
        ],
        "headers": {
            "Content-Type": "application/json",
        },
        "body": {
            "device": "{name}",
            "event_type": "{event_type}",
            "connected": "{data}",
        },
    }
    created = dispatcher.create_dispatch("connection_webhook", post_dispatch)
    print(f"create_dispatch -> {created}")

    # 2) Create a new SQL dispatch JSON
    sql_dispatch = {
        "dispatch_type": "sql",
        "connection_string": "postgresql://user:password@localhost:5432/mydatabase",
        "on_event": "tag",
        "retry_attempts": 2,
        "retry_backoff_seconds": 0.1,
        "filters": [
            {
                "key": "{name}",
                "value": "XPAD",
                "operator": "eq",
            },
            {
                "key": "{data[rssi]}",
                "value": -70,
                "operator": "gte",
            },
        ],
        "query": "INSERT INTO events (device, epc, rssi, ant) VALUES (:device, :epc, :rssi, :ant)",
        "params": {
            "device": "{name}",
            "epc": "{data[epc]}",
            "rssi": "{data[rssi]}",
            "ant": "{data[ant]}",
        },
    }
    created = dispatcher.create_dispatch("tag_sql", sql_dispatch)
    print(f"create_dispatch (sql) -> {created}")

    # 3) Edit an existing dispatch using deep merge
    edited = dispatcher.edit_dispatch(
        "connection_webhook",
        {
            "headers": {"X-Source": "smartx-rfid"},
            "retry_attempts": 5,
        },
        merge=True,
    )
    print(f"edit_dispatch -> {edited}")

    # 4) Show current dispatch list and one dispatch content
    print("dispatch files:", dispatcher.get_dispatch_names())
    print("connection_webhook content:", dispatcher.get_dispatch_content("connection_webhook"))

    # 5) Start dispatcher and enqueue different event types
    await dispatcher.start()

    await dispatcher.add_async("XPAD", "connection", True)
    await dispatcher.add_async("XPAD", "reading", True)
    await dispatcher.add_async("XPAD", "serial_number", "SN-000123456")
    await dispatcher.add_async(
        "XPAD",
        "tag",
        {
            "epc": "E2801170000002089910ABCD",
            "rssi": -58,
            "ant": 1,
            "timestamp": "2026-05-16T18:00:00Z",
        },
    )

    await dispatcher.flush(timeout=3)
    print("stats:", dispatcher.get_stats())

    # 6) Delete demo dispatches
    deleted_connection = dispatcher.delete_dispatch("connection_webhook")
    deleted_tag_sql = dispatcher.delete_dispatch("tag_sql")
    print(f"delete_dispatch connection_webhook -> {deleted_connection}")
    print(f"delete_dispatch tag_sql -> {deleted_tag_sql}")

    await dispatcher.stop(drain=True)


if __name__ == "__main__":
    asyncio.run(main())
