"""Small local catalog adapter for project-owned files."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

SUPPORTED = {".csv", ".json", ".jsonl", ".parquet", ".txt"}


def local_catalog(project: Path) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    for root in (project / "data", project / "datasets"):
        if not root.is_dir():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in SUPPORTED:
                continue
            item: dict[str, Any] = {
                "name": file.stem,
                "path": file.relative_to(project).as_posix(),
                "format": file.suffix.lower().lstrip("."),
            }
            if file.suffix.lower() == ".csv":
                try:
                    with file.open(newline="", encoding="utf-8-sig") as handle:
                        item["columns"] = next(csv.reader(handle), [])[:200]
                except (OSError, UnicodeError, csv.Error):
                    item["columns"] = []
            tables.append(item)
    return {"catalog": "local", "namespace": project.name, "tables": tables}
