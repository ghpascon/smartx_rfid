from pydantic import BaseModel, Field
from typing import Any


class EventSchema(BaseModel):
    event_type: str = Field("event", description="Type of the event")
    event_data: Any = Field(None, description="Associated data with the event")
