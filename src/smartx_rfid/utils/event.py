import logging


def on_event(name: str, event_type: str, event_data=None):
    """
    Default event handler for protocol events.

    This method can be overridden to handle specific events like
    connection status changes or received messages.

    Args:
            event_type: Type of event ('connection', 'receive', etc.)
            event_data: Associated data with the event
    """
    logging.info(f"{name} -> 🔔 Event: {event_type}, Data: {event_data}")
