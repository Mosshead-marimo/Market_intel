from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)
from anthropic.types import MessageParam, OutputConfigParam

from tradesentinel.platform.config import Settings
from tradesentinel.providers.contracts import (
    LanguageModelRequest,
    LanguageModelResponse,
    LanguageModelUsage,
    ProviderContext,
)
from tradesentinel.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderOutputError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tradesentinel.providers.interfaces import LanguageModelProvider


class AnthropicLanguageModelAdapter(LanguageModelProvider):
    def __init__(self, settings: Settings) -> None:
        if settings.anthropic_api_key is None:
            raise ProviderConfigurationError("anthropic", "ANTHROPIC_API_KEY is required.")
        self._model = settings.anthropic_model
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.llm_timeout_ms / 1_000,
        )

    async def generate(
        self, context: ProviderContext, request: LanguageModelRequest
    ) -> LanguageModelResponse:
        del context
        messages = [
            cast(
                MessageParam,
                {
                    "role": "user",
                    "content": json.dumps(request.input_payload, separators=(",", ":")),
                },
            )
        ]
        output_config = cast(
            OutputConfigParam,
            {"format": {"type": "json_schema", "schema": request.output_schema}},
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=request.max_output_tokens,
                system=request.system_prompt,
                messages=messages,
                output_config=output_config,
                tools=[],
            )
        except AuthenticationError as exc:
            raise ProviderAuthenticationError("anthropic") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitedError("anthropic", 1) from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError("anthropic") from exc
        except APIConnectionError as exc:
            raise ProviderUnavailableError("anthropic") from exc
        except APIStatusError as exc:
            raise ProviderUnavailableError("anthropic") from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            output = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderOutputError("anthropic") from exc
        if not isinstance(output, dict):
            raise ProviderOutputError("anthropic")
        return LanguageModelResponse(
            output=output,
            provider="anthropic",
            model=self._model,
            provider_request_id=response.id,
            finish_reason=response.stop_reason,
            usage=LanguageModelUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            created_at=datetime.now(UTC),
        )
