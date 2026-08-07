from pathlib import Path


def test_platform_never_imports_feature_modules() -> None:
    platform_root = Path("apps/api/src/tradesentinel/platform")
    for path in platform_root.rglob("*.py"):
        assert "tradesentinel.modules" not in path.read_text(encoding="utf-8"), path


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
