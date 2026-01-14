from pydantic import BaseModel, Field


class EventSchema(BaseModel):
    event_type: str = Field("event", description="Type of the event")
    event_data = Field(None, description="Associated data with the event")
