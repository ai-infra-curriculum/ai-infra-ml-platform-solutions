"""Minimal plugin system using Python's importlib + entry points."""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Protocol


class StoragePlugin(Protocol):
    name: str

    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes | None: ...


def load_storage_plugins() -> dict[str, StoragePlugin]:
    """Discover plugins via the 'ml_platform.storage' entry-point group."""
    plugins = {}
    for ep in entry_points(group="ml_platform.storage"):
        cls = ep.load()
        plugins[ep.name] = cls()
    return plugins


class LocalFSStorage:
    name = "local_fs"

    def __init__(self, root: str = "/tmp/storage"):
        from pathlib import Path
        self._root = Path(root)
        self._root.mkdir(exist_ok=True, parents=True)

    def put(self, key: str, data: bytes) -> None:
        (self._root / key).write_bytes(data)

    def get(self, key: str) -> bytes | None:
        p = self._root / key
        return p.read_bytes() if p.exists() else None
