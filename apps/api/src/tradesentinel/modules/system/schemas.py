from pydantic import BaseModel, ConfigDict


class PingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = "ping"
    dependencies: dict[str, object] = {}


class PingOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reply: str
    service: str
    version: str
