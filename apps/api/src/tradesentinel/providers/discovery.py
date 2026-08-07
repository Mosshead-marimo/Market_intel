from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.errors import DiscoveryError
from tradesentinel.platform.modules import ModuleLoader
from tradesentinel.platform.rate_limits import RateLimiter
from tradesentinel.providers.contracts import (
    ProviderDescriptor,
    ProviderKind,
    ProviderRateLimit,
)
from tradesentinel.providers.errors import ProviderRegistryError
from tradesentinel.providers.factory import ProviderFactory
from tradesentinel.providers.registry import ProviderRegistration, ProviderRegistry


class ProviderBootstrap:
    def __init__(
        self,
        registry: ProviderRegistry,
        resolver: DependencyResolver,
        rate_limiter: RateLimiter,
        selections: Mapping[ProviderKind, tuple[str, ...]],
    ) -> None:
        self.registry = registry
        self.resolver = resolver
        self.rate_limiter = rate_limiter
        self.selections = selections

    def load(self, loader: ModuleLoader, roots: tuple[Path, ...]) -> ProviderFactory:
        manifests = loader.discover(roots)
        staged = ProviderRegistry()
        for manifest in manifests:
            for declaration in manifest.providers:
                try:
                    descriptor = ProviderDescriptor(
                        kind=declaration.kind,
                        name=declaration.name,
                        class_path=declaration.class_path,
                        timeout_ms=declaration.timeout_ms,
                        rate_limit=ProviderRateLimit(**declaration.rate_limit.model_dump()),
                    )
                except ValidationError as exc:
                    raise ProviderRegistryError(
                        "A provider declaration is invalid.",
                        {
                            "module": manifest.name,
                            "provider": declaration.name,
                            "errors": exc.errors(include_url=False),
                        },
                    ) from exc
                staged.register(
                    ProviderRegistration(
                        descriptor=descriptor,
                        adapter_class=self._import_adapter(descriptor.class_path),
                    )
                )

        snapshot = self.resolver.snapshot()
        factory = ProviderFactory(staged, self.resolver, self.rate_limiter)
        try:
            factory.configure(self.selections)
            loader.load_manifests(manifests)
        except Exception:
            self.resolver.restore(snapshot)
            raise
        self.registry.restore(staged.list())
        factory.registry = self.registry
        return factory

    @staticmethod
    def _import_adapter(class_path: str) -> type[Any]:
        module_name, separator, attribute = class_path.partition(":")
        if not separator:
            raise DiscoveryError("Provider class paths must use 'module:Class'.")
        try:
            candidate = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError) as exc:
            raise DiscoveryError(
                "A provider adapter class could not be imported.",
                {"class_path": class_path},
            ) from exc
        if not inspect.isclass(candidate) or inspect.isabstract(candidate):
            raise DiscoveryError(
                "A declared provider adapter must be a concrete class.",
                {"class_path": class_path},
            )
        return candidate
