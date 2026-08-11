from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from tradesentinel.platform.config import Settings
from tradesentinel.providers.contracts import (
    LanguageModelRequest,
    LanguageModelResponse,
    LanguageModelUsage,
    ProviderContext,
)
from tradesentinel.providers.interfaces import LanguageModelProvider


class FakeLanguageModelProvider(LanguageModelProvider):
    requests: ClassVar[list[LanguageModelRequest]] = []

    async def generate(
        self, context: ProviderContext, request: LanguageModelRequest
    ) -> LanguageModelResponse:
        del context
        type(self).requests.append(request)
        if request.task == "planning":
            output = {
                "mode": "execute",
                "task": "conversation",
                "commands": [{"command": "/ping"}],
                "follow_up_questions": [],
            }
        else:
            evidence = request.input_payload["evidence"]
            assert isinstance(evidence, dict)
            records = evidence["records"]
            assert isinstance(records, list) and records
            first = records[0]
            assert isinstance(first, dict)
            output = {
                "claims": [
                    {
                        "claim_id": "claim_system_status",
                        "text": "The registered system check completed successfully.",
                        "evidence_ids": [first["evidence_id"]],
                    }
                ],
                "supportive": [],
                "contradictory": [],
                "uncertainties": [],
                "follow_up_questions": [
                    {
                        "id": "inspect_commands",
                        "label": "Inspect commands",
                        "prompt": "Which registered commands are available?",
                    }
                ],
            }
        return LanguageModelResponse(
            output=output,
            provider="fake_llm",
            model="deterministic-test-model",
            provider_request_id="fake-request",
            finish_reason="stop",
            usage=LanguageModelUsage(input_tokens=10, output_tokens=10),
            created_at=datetime.now(UTC),
        )


def llm_test_settings() -> Settings:
    tests_root = Path(__file__).parents[1]
    api_root = tests_root.parent
    return Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        llm_providers=("fake_llm",),
        module_roots=(
            api_root / "src" / "tradesentinel" / "modules",
            tests_root / "fixtures" / "llm_provider",
        ),
    )
