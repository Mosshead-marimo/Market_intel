from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar, cast, get_type_hints

from tradesentinel.platform.errors import DependencyResolutionError

DependencyT = TypeVar("DependencyT")


class DependencyResolver:
    def __init__(self) -> None:
        self._instances: dict[type[Any], object] = {}
        self._factories: dict[type[Any], Callable[[], object]] = {}

    def register_instance(self, dependency_type: type[DependencyT], instance: DependencyT) -> None:
        self._instances[dependency_type] = instance

    def register_factory(
        self, dependency_type: type[DependencyT], factory: Callable[[], DependencyT]
    ) -> None:
        self._factories[dependency_type] = factory

    def resolve(self, dependency_type: type[DependencyT]) -> DependencyT:
        return self._resolve(dependency_type, ())

    def _resolve(
        self, dependency_type: type[DependencyT], stack: tuple[type[Any], ...]
    ) -> DependencyT:
        if dependency_type in self._instances:
            return self._instances[dependency_type]  # type: ignore[return-value]
        if dependency_type in self._factories:
            instance = self._factories[dependency_type]()
            self._instances[dependency_type] = instance
            return instance  # type: ignore[return-value]
        if dependency_type in stack:
            chain = " -> ".join(item.__name__ for item in (*stack, dependency_type))
            raise DependencyResolutionError(dependency_type.__name__, f"dependency cycle: {chain}")
        if inspect.isabstract(dependency_type) or not inspect.isclass(dependency_type):
            raise DependencyResolutionError(dependency_type.__name__, "no provider is registered")
        try:
            signature = inspect.signature(dependency_type.__init__)
            hints = get_type_hints(dependency_type.__init__)
        except (TypeError, NameError) as exc:
            raise DependencyResolutionError(
                dependency_type.__name__, "constructor annotations could not be inspected"
            ) from exc
        arguments: dict[str, object] = {}
        for name, parameter in signature.parameters.items():
            if name == "self" or parameter.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue
            annotation = hints.get(name)
            if annotation is None:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise DependencyResolutionError(
                    dependency_type.__name__, f"constructor parameter '{name}' is untyped"
                )
            if not inspect.isclass(annotation):
                raise DependencyResolutionError(
                    dependency_type.__name__, f"constructor parameter '{name}' is not a class type"
                )
            arguments[name] = self._resolve(annotation, (*stack, dependency_type))
        try:
            instance = dependency_type(**arguments)
        except Exception as exc:
            raise DependencyResolutionError(
                dependency_type.__name__, "constructor raised an exception"
            ) from exc
        self._instances[dependency_type] = instance
        return cast(DependencyT, instance)
