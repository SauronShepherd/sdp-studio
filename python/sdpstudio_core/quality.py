"""Deterministic bounded quality evaluation for preview and local diagnostics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .debug import profile_rows


def evaluate_quality(
    node_type: str, config: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Evaluate one quality node without triggering Spark actions or writes."""
    failures: list[dict[str, Any]] = []
    passed_rows = rows
    if node_type == "quality.column_rule":
        column = str(config.get("column", ""))
        condition = str(config.get("condition", "")).strip()
        # The bounded evaluator supports the safe common predicates used by the
        # preview contract; arbitrary expressions remain runtime-owned.
        if condition in {"not_null", "not null"}:
            passed_rows = [row for row in rows if row.get(column) is not None]
        elif condition in {"non_empty", "not_empty"}:
            passed_rows = [row for row in rows if row.get(column) not in (None, "")]
        else:
            return {"status": "deferred", "checked": len(rows), "failures": [], "rows": rows}
    elif node_type == "quality.null_rate":
        column = str(config.get("column", ""))
        rate = sum(row.get(column) is None for row in rows) / len(rows) if rows else 0.0
        maximum = float(config.get("maxRate", 0.0) or 0.0)
        if rate > maximum:
            failures.append({"rule": "null_rate", "actual": rate, "maximum": maximum})
    elif node_type == "quality.uniqueness":
        columns = [str(value) for value in config.get("columns", [])]
        keys = [tuple(row.get(column) for column in columns) for row in rows]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        if duplicates:
            failures.append({"rule": "uniqueness", "duplicate_keys": duplicates})
    elif node_type == "quality.row_count_range":
        count = len(rows)
        minimum = int(config.get("minimum", 0))
        max_rows = int(config["maximum"]) if config.get("maximum") is not None else None
        if count < minimum or (max_rows is not None and count > max_rows):
            failures.append(
                {
                    "rule": "row_count_range",
                    "actual": count,
                    "minimum": minimum,
                    "maximum": max_rows,
                }
            )
    elif node_type == "quality.schema_contract":
        expected = config.get("schema")
        if not isinstance(expected, list):
            return {"status": "deferred", "checked": len(rows), "failures": [], "rows": rows}
        actual_names = sorted({key for row in rows for key in row})
        expected_names = sorted(
            str(item.get("name"))
            for item in expected
            if isinstance(item, dict) and item.get("name")
        )
        if actual_names != expected_names:
            failures.append(
                {
                    "rule": "schema_contract",
                    "actual_columns": actual_names,
                    "expected_columns": expected_names,
                }
            )
        passed_rows = rows
    elif node_type == "quality.profile_probe":
        columns = [str(value) for value in config.get("columns", [])]
        profile = profile_rows(rows, max_columns=len(columns) if columns else 100)
        return {
            "status": "passed",
            "checked": len(rows),
            "failures": [],
            "rows": rows,
            "profile": profile,
        }
    elif node_type == "quality.referential_sample":
        columns = [str(value) for value in config.get("columns", [])]
        reference = config.get("referenceRows")
        if not isinstance(reference, list) or not columns:
            return {"status": "deferred", "checked": len(rows), "failures": [], "rows": rows}
        reference_keys = {
            tuple(item.get(column) for column in columns)
            for item in reference
            if isinstance(item, dict)
        }
        missing = [
            row
            for row in rows
            if tuple(row.get(column) for column in columns) not in reference_keys
        ]
        if missing:
            failures.append(
                {"rule": "referential_sample", "missing_count": len(missing), "columns": columns}
            )
            passed_rows = [row for row in rows if row not in missing]
    elif node_type == "quality.quarantine_split":
        # A conservative split for the bounded preview predicates above.
        condition = str(config.get("condition", "")).strip()
        if condition in {"not_null", "not null", "non_empty", "not_empty"}:
            column = str(config.get("column", ""))
            passed_rows = [
                row for row in rows if row.get(column) is not None and row.get(column) != ""
            ]
            return {
                "status": "passed" if len(passed_rows) == len(rows) else "failed",
                "checked": len(rows),
                "failures": [],
                "rows": passed_rows,
                "quarantine": [row for row in rows if row not in passed_rows],
            }
        return {
            "status": "deferred",
            "checked": len(rows),
            "failures": [],
            "rows": rows,
            "quarantine": [],
        }
    else:
        return {"status": "deferred", "checked": len(rows), "failures": [], "rows": rows}
    failures.extend({"row": row} for row in rows if row not in passed_rows)
    return {
        "status": "failed" if failures else "passed",
        "checked": len(rows),
        "failures": failures,
        "rows": passed_rows,
    }
