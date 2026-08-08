from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tradesentinel.api.module_routes import ModuleApiRouterLoader
from tradesentinel.domain.instruments import (
    AssetType,
    InstrumentAutocompleteInput,
    InstrumentResolveInput,
    InstrumentSearchInput,
)
from tradesentinel.modules.instrument_resolution.repository import InstrumentRepositoryFactory
from tradesentinel.modules.instrument_resolution.service import (
    InstrumentResolutionService,
    normalize,
)
from tradesentinel.platform.errors import DiscoveryError
from tradesentinel.platform.persistence import PersistenceResources


def _service() -> InstrumentResolutionService:
    sessions = cast(async_sessionmaker[AsyncSession], None)
    return InstrumentResolutionService(
        InstrumentRepositoryFactory(PersistenceResources(backend="memory", sessions=sessions))
    )


def test_normalization_is_unicode_case_and_punctuation_stable() -> None:
    assert normalize("  Coca-Cola™  COMPANY ") == "coca cola company"
    assert normalize("Infosys, Ltd.") == "infosys ltd"


async def test_resolve_ticker_requires_exchange_when_cross_listed() -> None:
    service = _service()
    ambiguous = await service.resolve(InstrumentResolveInput(query="TCS"))
    assert ambiguous.status == "ambiguous"
    assert [(item.instrument.exchange, item.confidence) for item in ambiguous.candidates] == [
        ("BSE", 1.0),
        ("NSE", 1.0),
    ]

    resolved = await service.resolve(InstrumentResolveInput(query="tcs", exchange="nse"))
    assert resolved.status == "resolved"
    assert resolved.match is not None
    assert resolved.match.instrument.symbol == "TCS"
    assert resolved.match.instrument.exchange == "NSE"
    assert resolved.match.instrument.asset_type == AssetType.EQUITY
    assert "Tata Consultancy Services" in resolved.match.instrument.aliases


async def test_company_partial_alias_and_fuzzy_typo_matching() -> None:
    service = _service()
    partial = await service.search(InstrumentSearchInput(query="Tata Consul"))
    assert {item.instrument.exchange for item in partial.matches[:2]} == {"NSE", "BSE"}
    assert all(item.confidence == 0.90 for item in partial.matches[:2])

    alias = await service.resolve(InstrumentResolveInput(query="Google"))
    assert alias.status == "resolved"
    assert alias.match is not None
    assert alias.match.instrument.symbol == "GOOGL"
    assert alias.match.matched_on == "alias"
    assert alias.match.confidence == 0.98

    typo = await service.resolve(InstrumentResolveInput(query="Microsft"))
    assert typo.status == "resolved"
    assert typo.match is not None
    assert typo.match.instrument.symbol == "MSFT"
    assert 0.70 <= typo.match.confidence < 0.90


async def test_search_threshold_order_filters_and_limits() -> None:
    service = _service()
    result = await service.search(
        InstrumentSearchInput(query="reliance", asset_type=AssetType.EQUITY, limit=1)
    )
    assert len(result.matches) == 1
    assert result.matches[0].instrument.exchange == "BSE"
    assert result.matches[0].confidence == 1.0

    filtered = await service.search(InstrumentSearchInput(query="reliance", exchange="NSE"))
    assert [match.instrument.exchange for match in filtered.matches] == ["NSE"]

    missing = await service.resolve(InstrumentResolveInput(query="zzzzzzzzzz"))
    assert missing.status == "not_found"
    assert missing.match is None
    assert missing.candidates == ()


async def test_autocomplete_is_prefix_only() -> None:
    service = _service()
    result = await service.autocomplete(InstrumentAutocompleteInput(query="Alp"))
    assert [match.instrument.symbol for match in result.matches] == ["GOOGL"]
    fuzzy_only = await service.autocomplete(InstrumentAutocompleteInput(query="Microsft"))
    assert fuzzy_only.matches == ()


async def test_manifest_registers_capabilities_commands_and_http_routes(
    client: AsyncClient,
) -> None:
    capabilities = (await client.get("/api/v1/capabilities")).json()
    names = {item["name"] for item in capabilities}
    assert {"instrument.resolve", "instrument.search", "instrument.autocomplete"} <= names
    commands = (await client.get("/api/v1/commands")).json()
    assert {"/resolve", "/search"} <= {item["name"] for item in commands}

    search = await client.get("/api/v1/instruments/search?q=Apple")
    assert search.status_code == 200
    assert search.json()["matches"][0]["instrument"]["symbol"] == "AAPL"
    autocomplete = await client.get("/api/v1/instruments/autocomplete?q=Alp")
    assert autocomplete.json()["matches"][0]["instrument"]["symbol"] == "GOOGL"
    resolve = await client.get("/api/v1/instruments/resolve?q=TCS&exchange=NSE")
    assert resolve.json()["status"] == "resolved"
    assert resolve.json()["match"]["instrument"]["exchange"] == "NSE"


async def test_commands_execute_through_the_pipeline(client: AsyncClient) -> None:
    resolved = await client.post(
        "/api/v1/commands/execute", json={"command": "/resolve TCS --exchange NSE"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["result"]["data"]["status"] == "resolved"
    searched = await client.post(
        "/api/v1/commands/execute",
        json={"command": '/search "Tata Consultancy" --limit 2'},
    )
    assert searched.status_code == 200
    assert len(searched.json()["result"]["data"]["matches"]) == 2


def test_module_router_loader_rejects_invalid_entrypoints(tmp_path: Path) -> None:
    module = tmp_path / "invalid"
    module.mkdir()
    (module / "manifest.yaml").write_text(
        """name: invalid.router
version: 1.0.0
description: Invalid router
api_router: tradesentinel.modules.system.service:SystemService
capabilities:
  - name: invalid.router
    class_path: tradesentinel.modules.system.capability:SystemPingCapability
    description: Invalid router test
""",
        encoding="utf-8",
    )
    with pytest.raises(DiscoveryError, match="APIRouter"):
        ModuleApiRouterLoader().load((tmp_path,))
