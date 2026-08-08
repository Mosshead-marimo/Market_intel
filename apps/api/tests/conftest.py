from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from support.fake_market_provider import market_test_settings
from tradesentinel.api.app import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(market_test_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
