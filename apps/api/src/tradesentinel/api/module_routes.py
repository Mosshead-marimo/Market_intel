from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import APIRouter

from tradesentinel.platform.errors import DiscoveryError
from tradesentinel.platform.manifest import ManifestParser


class ModuleApiRouterLoader:
    def __init__(self, parser: ManifestParser | None = None) -> None:
        self._parser = parser or ManifestParser()

    def load(self, roots: tuple[Path, ...]) -> tuple[APIRouter, ...]:
        paths = sorted(
            {path.resolve() for root in roots for path in root.resolve().rglob("manifest.yaml")},
            key=lambda path: path.as_posix().casefold(),
        )
        routers: list[APIRouter] = []
        for path in paths:
            manifest = self._parser.parse(path)
            if manifest.api_router is not None:
                routers.append(self._import_router(manifest.api_router))
        return tuple(routers)

    @staticmethod
    def _import_router(class_path: str) -> APIRouter:
        module_name, separator, attribute = class_path.partition(":")
        if not separator:
            raise DiscoveryError("API router paths must use 'module:router'.")
        try:
            candidate = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError) as exc:
            raise DiscoveryError(
                "A module API router could not be imported.", {"class_path": class_path}
            ) from exc
        if not isinstance(candidate, APIRouter):
            raise DiscoveryError(
                "A module API router entrypoint must expose an APIRouter.",
                {"class_path": class_path},
            )
        return candidate
