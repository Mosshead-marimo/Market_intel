from pathlib import Path


def test_platform_never_imports_feature_modules() -> None:
    platform_root = Path("apps/api/src/tradesentinel/platform")
    for path in platform_root.rglob("*.py"):
        assert "tradesentinel.modules" not in path.read_text(encoding="utf-8"), path


def test_platform_never_imports_provider_domain_contracts() -> None:
    platform_root = Path("apps/api/src/tradesentinel/platform")
    for path in platform_root.rglob("*.py"):
        assert "tradesentinel.providers" not in path.read_text(encoding="utf-8"), path


def test_api_routes_do_not_import_database_models() -> None:
    routes = Path("apps/api/src/tradesentinel/api/routes.py").read_text(encoding="utf-8")
    assert "WorkflowRunRecord" not in routes
    assert "CapabilityRunRecord" not in routes


def test_modules_require_no_registration_plugin() -> None:
    modules_root = Path("apps/api/src/tradesentinel/modules")
    assert list(modules_root.rglob("plugin.py")) == []


def test_api_dispatches_through_execution_pipeline() -> None:
    routes = Path("apps/api/src/tradesentinel/api/routes.py").read_text(encoding="utf-8")
    assert "container.capabilities.get" not in routes
    assert "container.commands.parse" not in routes
    assert "container.pipeline.execute" in routes


def test_platform_has_no_module_specific_conditionals() -> None:
    platform_root = Path("apps/api/src/tradesentinel/platform")
    source = "\n".join(path.read_text(encoding="utf-8") for path in platform_root.rglob("*.py"))
    assert "system.ping" not in source
    assert "platform.system" not in source


def test_modules_keep_external_clients_inside_provider_adapters() -> None:
    modules_root = Path("apps/api/src/tradesentinel/modules")
    external_clients = {"httpx", "requests", "aiohttp", "urllib3"}
    for path in modules_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(
            f"import {client}" in source or f"from {client}" in source
            for client in external_clients
        ):
            relative_parts = path.relative_to(modules_root).parts
            assert "providers" in relative_parts and "adapters" in relative_parts, path


def test_shared_api_does_not_hardcode_instrument_capabilities() -> None:
    api_root = Path("apps/api/src/tradesentinel/api")
    source = "\n".join(path.read_text(encoding="utf-8") for path in api_root.rglob("*.py"))
    assert "instrument.search" not in source
    assert "instrument.resolve" not in source
    assert "instrument.autocomplete" not in source


def test_instrument_routes_and_capabilities_do_not_access_database_directly() -> None:
    module = Path("apps/api/src/tradesentinel/modules/instrument_resolution")
    for filename in ("api.py", "capability.py", "service.py"):
        source = (module / filename).read_text(encoding="utf-8")
        assert "sqlalchemy" not in source


def test_shared_api_does_not_hardcode_stock_market_capabilities() -> None:
    api_root = Path("apps/api/src/tradesentinel/api")
    source = "\n".join(path.read_text(encoding="utf-8") for path in api_root.rglob("*.py"))
    assert "stock.quote" not in source
    assert "stock_market_data" not in source


def test_stock_market_data_is_structured_and_provider_bound() -> None:
    module = Path("apps/api/src/tradesentinel/modules/stock_market_data")
    forbidden = ("httpx", "requests", "aiohttp", "openai", "anthropic", "sqlalchemy")
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(name in source for name in forbidden), path
    service = (module / "service.py").read_text(encoding="utf-8")
    assert "MarketDataProvider" in service


def test_shared_api_does_not_hardcode_research_capabilities() -> None:
    api_root = Path("apps/api/src/tradesentinel/api")
    source = "\n".join(path.read_text(encoding="utf-8") for path in api_root.rglob("*.py"))
    assert "research.news.search" not in source
    assert "research.report" not in source


def test_research_transport_and_logic_respect_boundaries() -> None:
    module = Path("apps/api/src/tradesentinel/modules/research")
    for filename in ("api.py", "capability.py", "service.py"):
        source = (module / filename).read_text(encoding="utf-8").casefold()
        assert "sqlalchemy" not in source
        assert "httpx" not in source
        assert "requests" not in source
        assert "openai" not in source
        assert "anthropic" not in source
    assert "NewsProvider" in (module / "service.py").read_text(encoding="utf-8")


def test_technical_analysis_is_pure_and_pipeline_bound() -> None:
    module = Path("apps/api/src/tradesentinel/modules/technical_analysis")
    forbidden = (
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "aiohttp",
        "openai",
        "anthropic",
        "langchain",
        "sqlalchemy",
        "pandas",
        "numpy",
        "talib",
        "tradesentinel.modules.stock_market_data",
    )
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8").casefold()
        assert not any(name in source for name in forbidden), path
    shared_api = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("apps/api/src/tradesentinel/api").rglob("*.py")
    )
    assert "technical.snapshot" not in shared_api
    assert "technical_analysis" not in shared_api


def test_fundamentals_is_provider_bound_and_transport_neutral() -> None:
    module = Path("apps/api/src/tradesentinel/modules/fundamentals")
    forbidden = (
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "aiohttp",
        "openai",
        "anthropic",
        "langchain",
        "sqlalchemy",
        "tradesentinel.modules.instrument_resolution",
        "tradesentinel.modules.stock_market_data",
    )
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8").casefold()
        assert not any(name in source for name in forbidden), path
    service = (module / "service.py").read_text(encoding="utf-8")
    assert "FundamentalsProvider" in service
    shared_api = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("apps/api/src/tradesentinel/api").rglob("*.py")
    )
    assert "fundamental.snapshot" not in shared_api
    assert "modules.fundamentals" not in shared_api


def test_stock_overview_order_and_targets_are_not_hardcoded_in_core() -> None:
    core_roots = (
        Path("apps/api/src/tradesentinel/platform"),
        Path("apps/api/src/tradesentinel/api"),
    )
    source = "\n".join(
        path.read_text(encoding="utf-8") for root in core_roots for path in root.rglob("*.py")
    )
    assert "stock.overview" not in source
    assert "stock_overview" not in source


def test_stock_overview_is_pipeline_bound_and_has_no_external_io() -> None:
    module = Path("apps/api/src/tradesentinel/modules/stock_overview")
    forbidden = (
        "httpx",
        "requests",
        "aiohttp",
        "openai",
        "anthropic",
        "langchain",
        "sqlalchemy",
        "tradesentinel.modules.instrument_resolution",
        "tradesentinel.modules.stock_market_data",
        "tradesentinel.modules.research",
        "tradesentinel.modules.public_sentiment",
        "tradesentinel.modules.technical_analysis",
        "tradesentinel.modules.fundamentals",
    )
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8").casefold()
        assert not any(name in source for name in forbidden), path
    assert "container.pipeline.execute" in (module / "api.py").read_text(encoding="utf-8")


def test_llm_sdks_are_confined_to_assistant_provider_adapters() -> None:
    source_root = Path("apps/api/src/tradesentinel")
    for path in source_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "from openai" in source or "from anthropic" in source:
            relative = path.relative_to(source_root).parts
            assert relative[:4] == (
                "modules",
                "llm_assistant",
                "providers",
                "adapters",
            ), path


def test_llm_assistant_does_not_import_feature_modules_or_calculation_libraries() -> None:
    module = Path("apps/api/src/tradesentinel/modules/llm_assistant")
    forbidden = (
        "tradesentinel.modules.stock_market_data",
        "tradesentinel.modules.research",
        "tradesentinel.modules.public_sentiment",
        "tradesentinel.modules.technical_analysis",
        "tradesentinel.modules.fundamentals",
        "pandas",
        "numpy",
        "talib",
    )
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8").casefold()
        assert not any(item in source for item in forbidden), path


def test_shared_api_has_no_assistant_target_conditionals() -> None:
    api = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("apps/api/src/tradesentinel/api").rglob("*.py")
    )
    assert "assistant.conversation" not in api
    assert "llm_assistant" not in api


def test_prediction_engine_remains_ml_only_and_internal() -> None:
    module = Path("apps/api/src/tradesentinel/modules/prediction_engine")
    forbidden = (
        "openai",
        "anthropic",
        "langchain",
        "tradesentinel.modules.llm_assistant",
        "tradesentinel.modules.stock_market_data",
        "tradesentinel.modules.technical_analysis",
        "tradesentinel.modules.fundamentals",
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
    )
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for dependency in forbidden:
            assert dependency not in source, (path, dependency)
    manifest = (module / "manifest.yaml").read_text(encoding="utf-8")
    assert "commands:" not in manifest
    assert "intents:" not in manifest
    assert "prediction_card" not in manifest
    assert "/api/v1/predictions" not in manifest


def test_market_shift_is_non_predictive_and_manifest_ordered() -> None:
    module = Path("apps/api/src/tradesentinel/modules/market_shift")
    forbidden = (
        "openai",
        "anthropic",
        "langchain",
        "sklearn",
        "tradesentinel.modules.prediction_engine",
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
    )
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        assert not any(item in source for item in forbidden), path
    manifest = (module / "manifest.yaml").read_text(encoding="utf-8")
    assert "market_shift.request" in manifest
    platform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("apps/api/src/tradesentinel/platform").rglob("*.py")
    )
    assert "market_shift.calculate" not in platform


def test_frontend_keeps_api_calls_and_prediction_admin_isolated() -> None:
    presentation = Path("apps/web/components/workspace.tsx").read_text(encoding="utf-8") + Path(
        "apps/web/components/response-component.tsx"
    ).read_text(encoding="utf-8")
    assert "fetch(" not in presentation
    assert "apiRequest(" not in presentation
    normal_routes = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("apps/web/app/workspace").rglob("*.tsx")
    )
    assert "PredictionAdmin" not in normal_routes
    assert "ModelPerformance" not in normal_routes
    assert "internalPrediction" not in normal_routes
