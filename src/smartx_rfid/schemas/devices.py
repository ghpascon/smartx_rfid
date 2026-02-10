from pydantic import BaseModel, Field
from typing import Optional
from typing import Literal


class GpoSchema(BaseModel):
    pin: int = Field(1)
    state: bool = Field(True)
    control: Optional[Literal["static", "pulsed"]] = Field("static")
    time: Optional[int] = Field(1000)
