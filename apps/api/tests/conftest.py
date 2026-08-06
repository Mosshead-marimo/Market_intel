from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from tradesentinel.api.app import create_app
from tradesentinel.platform.config import Settings


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(environment="test", persistence_backend="memory", event_backend="memory")
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
