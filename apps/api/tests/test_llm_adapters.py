from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from pydantic import SecretStr
from tradesentinel.modules.llm_assistant.providers.adapters.anthropic import (
    AnthropicLanguageModelAdapter,
)
from tradesentinel.modules.llm_assistant.providers.adapters.openai import (
    OpenAILanguageModelAdapter,
)
from tradesentinel.platform.config import Settings
from tradesentinel.providers.contracts import LanguageModelRequest, ProviderContext


class _Responses:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    async def create(self, **kwargs: object) -> object:
        self.arguments = kwargs
        return SimpleNamespace(
            output_text='{"claims": []}',
            id="openai-request",
            status="completed",
            usage=SimpleNamespace(input_tokens=12, output_tokens=4),
        )


class _Messages:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    async def create(self, **kwargs: object) -> object:
        self.arguments = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"claims": []}')],
            id="anthropic-request",
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=11, output_tokens=3),
        )


def _context() -> ProviderContext:
    return ProviderContext(request_id=uuid4(), correlation_id=uuid4())


def _request() -> LanguageModelRequest:
    return LanguageModelRequest(
        task="test",
        system_prompt="Return the schema.",
        input_payload={"evidence": []},
        output_schema={
            "type": "object",
            "properties": {"claims": {"type": "array", "items": {}}},
            "required": ["claims"],
            "additionalProperties": False,
        },
    )


async def test_openai_adapter_uses_strict_responses_schema_without_tools() -> None:
    adapter = OpenAILanguageModelAdapter(
        Settings(environment="test", openai_api_key=SecretStr("test-key"))
    )
    responses = _Responses()
    cast(Any, adapter)._client = SimpleNamespace(responses=responses)
    result = await adapter.generate(_context(), _request())
    assert result.provider == "openai"
    assert result.output == {"claims": []}
    assert responses.arguments["tools"] == []
    assert responses.arguments["store"] is False
    text = cast(dict[str, Any], responses.arguments["text"])
    assert text["format"]["strict"] is True


async def test_anthropic_adapter_uses_schema_output_without_tools() -> None:
    adapter = AnthropicLanguageModelAdapter(
        Settings(environment="test", anthropic_api_key=SecretStr("test-key"))
    )
    messages = _Messages()
    cast(Any, adapter)._client = SimpleNamespace(messages=messages)
    result = await adapter.generate(_context(), _request())
    assert result.provider == "anthropic"
    assert result.created_at <= datetime.now(UTC)
    assert messages.arguments["tools"] == []
    output_config = cast(dict[str, Any], messages.arguments["output_config"])
    assert output_config["format"]["type"] == "json_schema"
