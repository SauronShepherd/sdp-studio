from __future__ import annotations

import importlib
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

pycrdt_module: Any = None
with suppress(ImportError):
    pycrdt_module = importlib.import_module("pycrdt")

Doc: Any = getattr(pycrdt_module, "Doc", None)


def server_merge_available() -> bool:
    return Doc is not None


def merge_updates(updates: Iterable[bytes]) -> bytes:
    """Merge Yjs-compatible updates into one update, when pycrdt is installed."""
    if Doc is None:
        raise RuntimeError("Server collaboration merge requires the collaboration extra")
    document: Any = Doc()
    for update in updates:
        document.apply_update(update)
    return document.get_update()
