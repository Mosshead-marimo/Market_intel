from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from openai.types.responses import ResponseTextConfigParam

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


class OpenAILanguageModelAdapter(LanguageModelProvider):
    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None:
            raise ProviderConfigurationError("openai", "OPENAI_API_KEY is required.")
        self._model = settings.openai_model
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.llm_timeout_ms / 1_000,
        )

    async def generate(
        self, context: ProviderContext, request: LanguageModelRequest
    ) -> LanguageModelResponse:
        del context
        text_config = cast(
            ResponseTextConfigParam,
            {
                "format": {
                    "type": "json_schema",
                    "name": "tradesentinel_response",
                    "schema": request.output_schema,
                    "strict": True,
                }
            },
        )
        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=request.system_prompt,
                input=json.dumps(request.input_payload, separators=(",", ":")),
                max_output_tokens=request.max_output_tokens,
                text=text_config,
                store=False,
                tools=[],
            )
        except AuthenticationError as exc:
            raise ProviderAuthenticationError("openai") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitedError("openai", 1) from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError("openai") from exc
        except APIConnectionError as exc:
            raise ProviderUnavailableError("openai") from exc
        except APIStatusError as exc:
            raise ProviderUnavailableError("openai") from exc
        try:
            output = json.loads(response.output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderOutputError("openai") from exc
        if not isinstance(output, dict):
            raise ProviderOutputError("openai")
        usage = response.usage
        return LanguageModelResponse(
            output=output,
            provider="openai",
            model=self._model,
            provider_request_id=response.id,
            finish_reason=response.status,
            usage=LanguageModelUsage(
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
            ),
            created_at=datetime.now(UTC),
        )
