from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from tradesentinel.platform.chat import ConversationPlanner, response_chunks
from tradesentinel.platform.chat_persistence import InMemoryChatRepository
from tradesentinel.platform.contracts import (
    ChatSessionStatus,
    ChatTurnStatus,
    CommandExecutionRequest,
    IntentExecutionRequest,
)
from tradesentinel.platform.errors import ChatTurnActiveError, SessionArchivedError


async def _wait_for_terminal(client: AsyncClient, turn_id: str) -> dict[str, object]:
    for _ in range(100):
        response = await client.get(f"/api/v1/chat/turns/{turn_id}")
        body = response.json()
        if body["status"] in {"completed", "partial", "failed"}:
            return body
        await asyncio.sleep(0.01)
    raise AssertionError("chat turn did not complete")


async def test_explicit_mock_command_streams_and_persists_history(client: AsyncClient) -> None:
    client_message_id = str(uuid4())
    accepted = await client.post(
        "/api/v1/chat",
        json={"message": '/echo "Hello from chat"', "client_message_id": client_message_id},
    )
    assert accepted.status_code == 202
    turn_id = accepted.json()["turn_id"]
    session_id = accepted.json()["session_id"]
    turn = await _wait_for_terminal(client, turn_id)
    assert turn["status"] == "completed", turn

    stream = await client.get(f"/api/v1/chat/turns/{turn_id}/events")
    assert stream.status_code == 200
    assert "event: status" in stream.text
    assert "event: typing" in stream.text
    assert "event: progress" in stream.text
    assert "event: response" in stream.text
    assert "event: component" in stream.text
    assert "event: complete" in stream.text

    history = await client.get(f"/api/v1/chat/sessions/{session_id}")
    messages = history.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert "deterministic mock response" in messages[1]["content"]
    assert messages[1]["response"]["trace"] == [
        "conversation.mock_understand",
        "conversation.mock_reply",
    ]

    duplicate = await client.post(
        "/api/v1/chat",
        json={"message": '/echo "Hello from chat"', "client_message_id": client_message_id},
    )
    assert duplicate.json()["turn_id"] == turn_id


async def test_chat_sessions_can_be_renamed_archived_and_are_owner_scoped(
    client: AsyncClient,
) -> None:
    created = await client.post("/api/v1/chat/sessions", json={"title": "First"})
    session_id = created.json()["id"]
    renamed = await client.patch(f"/api/v1/chat/sessions/{session_id}", json={"title": "Renamed"})
    assert renamed.json()["title"] == "Renamed"
    archived = await client.patch(f"/api/v1/chat/sessions/{session_id}", json={"archived": True})
    assert archived.json()["status"] == "archived"
    listing = await client.get("/api/v1/chat/sessions?archived=true")
    assert listing.json()["items"][0]["id"] == session_id

    client.cookies.clear()
    response = await client.get(
        f"/api/v1/chat/sessions/{session_id}", headers={"X-Client-ID": str(uuid4())}
    )
    assert response.status_code == 404


def test_conversation_planner_and_stream_chunking_are_deterministic() -> None:
    planner = ConversationPlanner()
    assert isinstance(planner.request_for(" /ping "), CommandExecutionRequest)
    assert isinstance(planner.request_for("hello"), IntentExecutionRequest)
    chunks = response_chunks("one two three four", max_characters=8)
    assert chunks == ("one two ", "three ", "four")
    assert "".join(chunks) == "one two three four"


async def test_repository_enforces_active_turn_archive_and_context_window() -> None:
    repository = InMemoryChatRepository()
    principal = "anonymous:test"
    session = await repository.create_session(principal)
    first = await repository.accept_turn(
        principal,
        session_id=session.id,
        client_message_id=uuid4(),
        content="first",
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert first.turn.status == ChatTurnStatus.QUEUED
    try:
        await repository.accept_turn(
            principal,
            session_id=session.id,
            client_message_id=uuid4(),
            content="second",
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
    except ChatTurnActiveError:
        pass
    else:
        raise AssertionError("parallel turn was accepted")

    await repository.fail_turn(
        principal,
        first.turn.id,
        error=_error(),
    )
    archived = await repository.update_session(principal, session.id, title=None, archived=True)
    assert archived.status == ChatSessionStatus.ARCHIVED
    try:
        await repository.accept_turn(
            principal,
            session_id=session.id,
            client_message_id=uuid4(),
            content="third",
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
    except SessionArchivedError:
        pass
    else:
        raise AssertionError("archived session accepted a turn")


async def test_repository_reclaims_only_expired_active_turns() -> None:
    repository = InMemoryChatRepository()
    principal = "anonymous:lease-test"
    accepted = await repository.accept_turn(
        principal,
        session_id=None,
        client_message_id=uuid4(),
        content="lease test",
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    claimed = await repository.claim_turn(principal, accepted.turn.id)
    assert claimed is not None
    assert claimed.attempt == 1
    assert await repository.claim_turn(principal, accepted.turn.id) is None

    expired = claimed.model_copy(
        update={"lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    repository.turns[claimed.id] = (principal, expired)
    reclaimed = await repository.claim_turn(principal, claimed.id)
    assert reclaimed is not None
    assert reclaimed.attempt == 2
    assert reclaimed.started_at == claimed.started_at


def _error():
    from tradesentinel.platform.contracts import ApiErrorDetail

    return ApiErrorDetail(code="TEST", message="safe")
