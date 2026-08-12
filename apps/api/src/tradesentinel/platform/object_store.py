from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class ObjectStore(ABC):
    @abstractmethod
    async def put(self, key: str, value: bytes) -> StoredObject: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...


class InMemoryObjectStore(ObjectStore):
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, value: bytes) -> StoredObject:
        _validate_key(key)
        self._objects[key] = bytes(value)
        return StoredObject(key, len(value), sha256(value).hexdigest())

    async def get(self, key: str) -> bytes:
        _validate_key(key)
        return self._objects[key]

    async def delete(self, key: str) -> None:
        _validate_key(key)
        self._objects.pop(key, None)


class FileObjectStore(ObjectStore):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        _validate_key(key)
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise ValueError("object key escapes the configured root")
        return path

    async def put(self, key: str, value: bytes) -> StoredObject:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                handle.write(value)
                temporary = Path(handle.name)
            temporary.replace(path)

        await asyncio.to_thread(write)
        return StoredObject(key, len(value), sha256(value).hexdigest())

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)


def _validate_key(key: str) -> None:
    if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
        raise ValueError("invalid object key")
