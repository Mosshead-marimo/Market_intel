from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from httpx import AsyncClient
from tradesentinel.domain.assistant import AssistantGeneratedOutput, EvidencePacket
from tradesentinel.modules.llm_assistant.evidence import EvidencePolicy
from tradesentinel.platform.contracts import EvidenceKind, EvidenceRecord, GroundedClaim


def _packet(value: str = "RSI: 54.2") -> EvidencePacket:
    return EvidencePacket(
        question="Explain the result",
        records=(
            EvidenceRecord(
                evidence_id="ev_0123456789abcdef",
                kind=EvidenceKind.CALCULATED_METRIC,
                title="RSI",
                value=value,
                producer="technical.rsi",
                timestamp=datetime.now(UTC),
                capability="technical.rsi",
                json_path="data.latest",
            ),
        ),
    )


def test_evidence_policy_rejects_unknown_numbers_and_prohibited_generation() -> None:
    policy = EvidencePolicy()
    unsupported = AssistantGeneratedOutput(
        claims=(
            GroundedClaim(
                claim_id="claim_bad",
                text="RSI is 61.4, so buy with a 70% chance of gains.",
                evidence_ids=("ev_0123456789abcdef",),
            ),
        )
    )
    violations = policy.violations(unsupported, _packet())
    assert "claim_bad:prohibited_financial_generation" in violations
    assert any("unsupported_number:61.4" in item for item in violations)
    assert any("unsupported_number:70%" in item for item in violations)


def test_evidence_policy_accepts_verbatim_precomputed_values() -> None:
    output = AssistantGeneratedOutput(
        claims=(
            GroundedClaim(
                claim_id="claim_valid",
                text="The reported RSI is 54.2.",
                evidence_ids=("ev_0123456789abcdef",),
            ),
        )
    )
    assert EvidencePolicy().violations(output, _packet()) == ()


async def _wait(client: AsyncClient, turn_id: str) -> dict[str, object]:
    for _ in range(100):
        response = await client.get(f"/api/v1/chat/turns/{turn_id}")
        body: dict[str, object] = response.json()
        if body["status"] in {"completed", "partial", "failed"}:
            return body
        await asyncio.sleep(0.01)
    raise AssertionError("assistant turn did not finish")


async def test_natural_language_chat_is_grounded_and_buffered(llm_client: AsyncClient) -> None:
    accepted = await llm_client.post(
        "/api/v1/chat",
        json={"message": "Is the system available?", "client_message_id": str(uuid4())},
    )
    assert accepted.status_code == 202
    turn_id = accepted.json()["turn_id"]
    turn = await _wait(llm_client, turn_id)
    assert turn["status"] == "completed"

    stream = await llm_client.get(f"/api/v1/chat/turns/{turn_id}/events")
    assert "Selecting registered commands" in stream.text
    assert "Synthesizing validated evidence" in stream.text
    assert stream.text.index("Evidence validation completed") < stream.text.index("event: response")
    assert "cited_narrative" in stream.text
    assert "follow_up_questions" in stream.text


async def test_unconfigured_llm_returns_typed_failure(client: AsyncClient) -> None:
    accepted = await client.post(
        "/api/v1/chat",
        json={"message": "Explain the market", "client_message_id": str(uuid4())},
    )
    turn = await _wait(client, accepted.json()["turn_id"])
    assert turn["status"] == "failed"
    error = turn["error"]
    assert isinstance(error, dict)
    assert error["code"] == "LLM_NOT_CONFIGURED"
