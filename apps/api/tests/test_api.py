from httpx import AsyncClient


async def test_platform_discovery_and_ping(client: AsyncClient) -> None:
    capabilities = await client.get("/api/v1/capabilities")
    assert capabilities.status_code == 200
    assert "system.ping" in {item["name"] for item in capabilities.json()}

    response = await client.post("/api/v1/commands/execute", json={"command": "/ping"})
    assert response.status_code == 200
    assert response.json()["result"]["data"]["reply"] == "pong"
    assert response.json()["response"]["text"] == "TradeSentinel platform is responding."
    assert response.json()["response"]["trace"] == ["system.ping"]
    assert response.headers["x-request-id"]


async def test_future_capability_returns_typed_501(client: AsyncClient) -> None:
    response = await client.get("/api/v1/predictions/00000000-0000-4000-8000-000000000001")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "CAPABILITY_NOT_INSTALLED"
    assert response.json()["request_id"]


async def test_system_workflow_is_persisted(client: AsyncClient) -> None:
    response = await client.post("/api/v1/workflows/system.health/execute", json={})
    assert response.status_code == 200
    run_id = response.json()["result"]["run_id"]
    run = await client.get(f"/api/v1/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
