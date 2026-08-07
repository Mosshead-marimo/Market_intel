from pydantic import BaseModel, ConfigDict, Field, JsonValue


class MockConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=20_000)
    dependencies: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)


class MockUnderstanding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    normalized_message: str
    word_count: int


class MockReply(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reply: str
    mode: str = "deterministic_mock"
