from __future__ import annotations

import ast
import hashlib
import json
import math
import operator
import re
from collections import defaultdict, deque
from collections.abc import Iterable
from statistics import mean, median, pstdev
from typing import Any, cast

from .graph import GraphIndex
from .models import PipelineDocument, Problem

_PLAN_NODE = re.compile(
    r"^(?P<indent>\s*)(?:\+-\s*)?(?:\*\(\d+\)\s*)?(?P<name>[A-Za-z][A-Za-z0-9_]+)(?:\s|$)"
)
_KNOWN_PLAN_OPERATORS = {
    "Aggregate",
    "BroadcastHashJoin",
    "BroadcastNestedLoopJoin",
    "CartesianProduct",
    "CollectLimit",
    "Exchange",
    "Expand",
    "Filter",
    "Generate",
    "HashAggregate",
    "Join",
    "Project",
    "Range",
    "Scan",
    "Sort",
    "SortMergeJoin",
    "Union",
    "Window",
    "WholeStageCodegen",
    "ShuffledHashJoin",
    "BroadcastExchange",
    "BatchEvalPython",
    "ArrowEvalPython",
    "PythonUDF",
    "PythonUdtf",
}
_TRACE_CONTRIBUTION_LIMIT = 3


def parse_explain_plan(explain: str) -> dict[str, Any]:
    """Parse Spark explain text without failing on version-specific operators."""
    nodes: list[dict[str, Any]] = []
    raw_lines: list[str] = []
    phase = "unknown"
    for number, line in enumerate(explain.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("==") and stripped.endswith("=="):
            heading = stripped.strip("= ").lower()
            phase = {
                "parsed logical plan": "parsed",
                "analyzed logical plan": "analyzed",
                "optimized logical plan": "optimized",
                "physical plan": "physical",
            }.get(heading, "unknown")
            continue
        if not stripped or stripped.startswith("-"):
            continue
        match = _PLAN_NODE.match(line)
        if not match or match.group("name") not in _KNOWN_PLAN_OPERATORS:
            raw_lines.append(line)
            continue
        raw = line.rstrip()
        node = {
            "id": f"plan-{len(nodes) + 1}",
            "operator": match.group("name"),
            "depth": len(match.group("indent")),
            "line": number,
            "phase": phase,
            "raw": raw,
        }
        # Keep useful execution metadata in the normalized representation.  Spark
        # changes node IDs and expression details between versions, so these are
        # deliberately derived from stable operator text rather than persisted IDs.
        lowered = raw.lower()
        if "broadcast" in lowered:
            node["join_strategy"] = "broadcast"
        elif "sortmerge" in lowered or "sort merge" in lowered:
            node["join_strategy"] = "sort_merge"
        elif "shuffledhash" in lowered or "shuffled hash" in lowered:
            node["join_strategy"] = "shuffled_hash"
        partition = re.search(r"(?:partitioning|partitions?)\([^)]*,\s*(\d+)\)", raw, re.I)
        if partition:
            node["partitioning"] = int(partition.group(1))
        exchange = re.search(r"(Exchange|BroadcastExchange)\s+([^\n]+)", raw, re.I)
        if exchange:
            node["exchange"] = re.sub(r"\bid=\d+\b", "id=?", exchange.group(0), flags=re.I)
        nodes.append(node)
    normalized = [
        {
            key: (
                re.sub(r"#\d+", "#?", value) if key == "raw" and isinstance(value, str) else value
            )
            for key, value in node.items()
            if key not in {"line", "id"}
        }
        for node in nodes
    ]
    return {
        "nodes": nodes,
        "normalized_nodes": normalized,
        "raw_lines": raw_lines,
        "node_count": len(nodes),
        "phases": sorted({node["phase"] for node in nodes}),
    }


def plan_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    before_nodes = left.get("nodes", [])
    after_nodes = right.get("nodes", [])
    before = [str(item.get("operator")) for item in before_nodes]
    after = [str(item.get("operator")) for item in after_nodes]
    before_phases = [str(item.get("phase", "unknown")) for item in before_nodes]
    after_phases = [str(item.get("phase", "unknown")) for item in after_nodes]
    operations: list[dict[str, Any]] = []
    for index in range(max(len(before_nodes), len(after_nodes))):
        old = before_nodes[index] if index < len(before_nodes) else None
        new = after_nodes[index] if index < len(after_nodes) else None
        if old is None and new is not None:
            operations.append({"op": "add", "index": index, "node": new})
        elif new is None and old is not None:
            operations.append({"op": "remove", "index": index, "node": old})
        elif old and new and old.get("operator") != new.get("operator"):
            operations.append({"op": "replace", "index": index, "before": old, "after": new})

    def attribute_changes(key: str) -> list[dict[str, Any]]:
        changes = []
        for index, (old, new) in enumerate(zip(before_nodes, after_nodes, strict=False)):
            if old.get(key) != new.get(key) and (
                old.get(key) is not None or new.get(key) is not None
            ):
                changes.append({"index": index, "before": old.get(key), "after": new.get(key)})
        return changes

    return {
        "added_operators": sorted(set(after) - set(before)),
        "removed_operators": sorted(set(before) - set(after)),
        "changed": before != after,
        "phase_changes": [
            {"before": old, "after": new, "index": index}
            for index, (old, new) in enumerate(zip(before_phases, after_phases, strict=False))
            if old != new
        ],
        "join_strategy_changes": attribute_changes("join_strategy"),
        "exchange_changes": attribute_changes("exchange"),
        "partitioning_changes": attribute_changes("partitioning"),
        "metric_changes": attribute_changes("metrics"),
        "before_count": len(before),
        "after_count": len(after),
        "operations": operations,
    }


def static_debug_plan(document: PipelineDocument) -> dict[str, Any]:
    index = GraphIndex(document)
    order = index.topological_order()
    risks: list[Problem] = []
    rows = []
    for ordinal, node_id in enumerate(order, start=1):
        node = index.nodes[node_id]
        risk = "low"
        reason = "Narrow or source/output operation"
        if node.type == "transform.join":
            risk = "high"
            reason = "Join commonly introduces shuffle and skew risk"
            risks.append(
                Problem(
                    code="SDPS-DBG-101",
                    severity="warning",
                    message=reason,
                    node_id=node.id,
                    remediation="Inspect join keys, partition balance, and Spark physical plan.",
                )
            )
        elif node.type == "transform.aggregate":
            risk = "high"
            reason = "Aggregation commonly introduces shuffle"
            risks.append(
                Problem(
                    code="SDPS-DBG-102",
                    severity="warning",
                    message=reason,
                    node_id=node.id,
                    remediation="Check group-key cardinality and skew before production.",
                )
            )
        elif node.type in {"transform.distinct"}:
            risk = "medium"
            reason = "Global deduplication can trigger shuffle"
        elif node.type == "transform.watermark":
            risk = "medium"
            reason = "Stateful streaming behavior depends on event-time distribution"
        rows.append(
            {
                "ordinal": ordinal,
                "node_id": node.id,
                "type": node.type,
                "risk": risk,
                "reason": reason,
            }
        )
    return {"nodes": rows, "risks": [p.model_dump() for p in risks]}


def row_trace(document: PipelineDocument, node_id: str) -> dict[str, Any]:
    index = GraphIndex(document)
    if node_id not in index.nodes:
        return {"path": [], "error": "Node not found"}
    path = []
    for current_id in index.trace_to_sources(node_id):
        node = index.nodes[current_id]
        step: dict[str, Any] = {"node_id": node.id, "type": node.type, "config": node.config}
        if node.type == "transform.filter":
            step["effect"] = f"Row survives when: {node.config.get('expression', '')}"
        elif node.type == "transform.select":
            step["effect"] = "Projection: " + ", ".join(node.config.get("columns", []))
        elif node.type == "transform.derive":
            step["effect"] = f"Derive {node.config.get('name')} := {node.config.get('expression')}"
        elif node.type == "transform.aggregate":
            step["effect"] = (
                "Aggregation changes row identity; tracing becomes group-level after this step."
            )
        elif node.type == "transform.join":
            step["effect"] = (
                f"Join ({node.config.get('how', 'inner')}) on {node.config.get('condition', '<implicit>')}"
            )
        path.append(step)
    return {"path": path}


_TRACE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_TRACE_CMPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
}


def _trace_expr(expression: str, row: dict[str, Any]) -> Any:
    """Evaluate the bounded expression subset used by visual row tracing."""
    normalized = expression.replace("<>", "!=")
    if "=" in normalized and "==" not in normalized and "!=" not in normalized:
        normalized = normalized.replace("=", "==", 1)
    tree = ast.parse(normalized, mode="eval")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name):
            return row.get(node.id)
        if isinstance(node, ast.Constant) and isinstance(
            node.value, str | int | float | bool | type(None)
        ):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not | ast.USub | ast.UAdd):
            value = visit(node.operand)
            return (
                (not value)
                if isinstance(node.op, ast.Not)
                else (-value if isinstance(node.op, ast.USub) else +value)
            )
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And | ast.Or):
            values = [visit(value) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.BinOp) and type(node.op) in _TRACE_BINOPS:
            return _TRACE_BINOPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                if type(op) not in _TRACE_CMPS or not _TRACE_CMPS[type(op)](
                    left, visit(comparator)
                ):
                    return False
                left = visit(comparator)
            return True
        raise ValueError("expression contains an unsupported trace construct")

    return visit(tree)


def execute_row_trace(
    document: PipelineDocument,
    node_id: str,
    rows: list[dict[str, Any]],
    *,
    max_rows: int = 200,
    rows_by_source: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Execute a side-effect-free, bounded trace over supported visual operators.

    ``rows`` remains the single-input compatibility path.  Multi-source callers
    can provide ``rows_by_source`` keyed by source node id so the trace does not
    incorrectly feed one source's sample into every source branch.
    """
    index = GraphIndex(document)
    if node_id not in index.nodes:
        return {"ok": False, "code": "SDPS-TRACE-001", "message": "Node not found"}
    if not 1 <= max_rows <= 200:
        return {
            "ok": False,
            "code": "SDPS-TRACE-002",
            "message": "Trace limit must be between 1 and 200",
        }
    current: dict[str, list[dict[str, Any]]] = {}
    trace_statuses: dict[str, str] = {}
    steps: list[dict[str, Any]] = []
    unsupported: list[dict[str, str]] = []
    bounded = [dict(row) for row in rows[:max_rows]]
    source_samples = {
        str(source_id): [dict(row) for row in source_rows[:max_rows]]
        for source_id, source_rows in (rows_by_source or {}).items()
    }
    for current_id in index.topological_order():
        node = index.nodes[current_id]
        parents = [edge.from_.node for edge in index.incoming.get(current_id, [])]
        inputs = [current.get(parent, bounded) for parent in parents]
        trace_status = (
            "unknown"
            if any(trace_statuses.get(parent) == "unknown" for parent in parents)
            else "known"
        )
        try:
            if node.type.startswith("source."):
                output = source_samples.get(current_id, bounded)
            elif node.type == "transform.filter":
                output = [
                    row
                    for row in (inputs[0] if inputs else [])
                    if bool(_trace_expr(str(node.config.get("expression", "")), row))
                ]
            elif node.type == "transform.select":
                columns = [str(value) for value in node.config.get("columns", [])]
                output = [
                    {column: row.get(column) for column in columns}
                    for row in (inputs[0] if inputs else [])
                ]
            elif node.type == "transform.derive":
                name = str(node.config.get("name", "derived"))
                output = [
                    {**row, name: _trace_expr(str(node.config.get("expression", "")), row)}
                    for row in (inputs[0] if inputs else [])
                ]
            elif node.type == "transform.rename":
                mapping = node.config.get("mapping") or {}
                output = [
                    {str(mapping.get(key, key)): value for key, value in row.items()}
                    for row in (inputs[0] if inputs else [])
                ]
            elif node.type == "transform.cast":
                column = str(node.config.get("column", ""))
                data_type = str(node.config.get("dataType", "")).lower()

                def cast_value(value: Any, target_type: str = data_type) -> Any:
                    if value is None:
                        return None
                    if target_type in {"int", "integer"}:
                        return int(value)
                    if target_type in {"long", "bigint"}:
                        return int(value)
                    if target_type in {"float", "double"}:
                        return float(value)
                    if target_type in {"string", "varchar"}:
                        return str(value)
                    raise ValueError(f"unsupported cast type: {target_type}")

                output = [
                    {**row, column: cast_value(row.get(column))}
                    for row in (inputs[0] if inputs else [])
                ]
            elif node.type == "transform.union":
                output = [row for part in inputs for row in part]
            elif node.type == "transform.join":
                left = inputs[0] if inputs else []
                right = inputs[1] if len(inputs) > 1 else []
                condition = str(node.config.get("condition", ""))
                match = (
                    ast.parse(condition.replace("=", "==", 1), mode="eval") if condition else None
                )
                output = []
                for left_row in left:
                    for right_row in right:
                        if (
                            match
                            and isinstance(match.body, ast.Compare)
                            and isinstance(match.body.left, ast.Attribute)
                        ):
                            left_key = left_row.get(match.body.left.attr)
                            comparator = match.body.comparators[0]
                            right_key = (
                                right_row.get(comparator.attr)
                                if isinstance(comparator, ast.Attribute)
                                else None
                            )
                            if left_key != right_key:
                                continue
                        output.append({**left_row, **right_row})
            elif node.type == "transform.aggregate":
                source_rows = inputs[0] if inputs else []
                group_by = [str(value) for value in node.config.get("groupBy", [])]
                grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
                for row in source_rows:
                    grouped[tuple(row.get(column) for column in group_by)].append(row)
                aggregations = node.config.get("aggregations", []) or [
                    {"expression": "count(*)", "alias": "row_count"}
                ]
                output = []
                trace_summary = []
                for key, members in sorted(grouped.items(), key=lambda item: repr(item[0])):
                    result = dict(zip(group_by, key, strict=True))
                    for aggregation in aggregations:
                        expression = str(aggregation.get("expression", "count(*)")).strip()
                        alias = str(aggregation.get("alias", expression))
                        aggregate_match = re.fullmatch(
                            r"(?i)(count|sum|avg|min|max)\s*\(\s*([\w*]+)\s*\)", expression
                        )
                        if not aggregate_match:
                            raise ValueError(f"unsupported aggregate expression: {expression}")
                        function, column = (
                            aggregate_match.group(1).lower(),
                            aggregate_match.group(2),
                        )
                        values = [
                            row.get(column)
                            for row in members
                            if column == "*" or row.get(column) is not None
                        ]
                        numeric_values = [
                            value for value in values if isinstance(value, int | float)
                        ]
                        value: Any = None
                        if function == "count":
                            value = len(members) if column == "*" else len(values)
                        elif not values:
                            value = None
                        elif function == "sum":
                            value = sum(numeric_values)
                        elif function == "avg":
                            value = sum(numeric_values) / len(numeric_values)
                        elif function == "min":
                            value = min(numeric_values)
                        else:
                            value = max(numeric_values)
                        result[alias] = value
                    output.append(result)
                    trace_summary.append(
                        {
                            "group": dict(zip(group_by, key, strict=True)),
                            "input_row_count": len(members),
                            "trace_row_ids": list(
                                range(min(len(members), _TRACE_CONTRIBUTION_LIMIT))
                            ),
                            "trace_overflow": len(members) > _TRACE_CONTRIBUTION_LIMIT,
                        }
                    )
            elif node.type == "transform.explode":
                column = str(node.config.get("column", ""))
                output = [
                    {**row, column: item}
                    for row in (inputs[0] if inputs else [])
                    for item in (row.get(column) or [])
                ]
            elif node.type.startswith("dataset.") or node.type.startswith("sink."):
                output = inputs[0] if inputs else []
            else:
                unsupported.append({"node_id": current_id, "type": node.type})
                # Custom code can change row identity/schema in ways this
                # bounded interpreter cannot inspect. Preserve the rows for
                # continuity, but mark downstream lineage as unknown.
                trace_status = "unknown"
                output = inputs[0] if inputs else []
        except (ValueError, TypeError, ZeroDivisionError, SyntaxError) as exc:
            return {
                "ok": False,
                "code": "SDPS-TRACE-003",
                "node_id": current_id,
                "message": str(exc),
                "steps": steps,
            }
        current[current_id] = output[:max_rows]
        trace_statuses[current_id] = trace_status
        step = {
            "node_id": current_id,
            "type": node.type,
            "input_count": sum(len(part) for part in inputs),
            "output_count": len(current[current_id]),
            "rows": current[current_id],
            "trace_status": trace_status,
        }
        if node.type == "transform.aggregate":
            step["trace_summary"] = trace_summary
        steps.append(step)
        if current_id == node_id:
            break
    return {
        "ok": True,
        "trace_mode": "sample",
        "execution_backed": False,
        "input_row_count": len(bounded),
        "provenance": "caller_supplied_rows",
        "node_id": node_id,
        "rows": current.get(node_id, []),
        "steps": steps,
        "unsupported": unsupported,
    }


def execute_row_trace_spark(
    document: PipelineDocument,
    node_id: str,
    rows: list[dict[str, Any]],
    *,
    max_rows: int = 200,
    rows_by_source: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Execute the trace subgraph with Spark DataFrame transformations.

    This is intentionally opt-in and lazy-imported so the default product does
    not require Spark. Unsupported/custom operators fail explicitly, allowing
    callers to choose the bounded interpreter fallback without mislabeling it.
    """
    try:
        from pyspark.sql import SparkSession
        from pyspark.sql import functions as F
    except ImportError as exc:
        raise RuntimeError("Spark Row Trace requires the pipelines runtime") from exc
    if not 1 <= max_rows <= 200:
        raise ValueError("Trace limit must be between 1 and 200")
    index = GraphIndex(document)
    if node_id not in index.nodes:
        return {"ok": False, "code": "SDPS-TRACE-001", "message": "Node not found"}
    spark = SparkSession.builder.master("local[2]").appName("sdpstudio-row-trace").getOrCreate()
    frames: dict[str, Any] = {}
    snapshots: list[dict[str, Any]] = []
    source_samples = rows_by_source or {}
    try:
        for current_id in index.topological_order():
            node = index.nodes[current_id]
            parents = index.incoming.get(current_id, [])
            inputs = [frames[edge.from_.node] for edge in parents]
            if node.type.startswith("source."):
                sample = source_samples.get(current_id, rows)
                frames[current_id] = spark.createDataFrame(sample[:max_rows])
            elif node.type == "transform.filter":
                frames[current_id] = inputs[0].filter(F.expr(str(node.config["expression"])))
            elif node.type == "transform.select":
                frames[current_id] = inputs[0].select(
                    *[F.col(str(c)) for c in node.config["columns"]]
                )
            elif node.type == "transform.derive":
                frames[current_id] = inputs[0].withColumn(
                    str(node.config.get("name", "derived")), F.expr(str(node.config["expression"]))
                )
            elif node.type == "transform.rename":
                frames[current_id] = inputs[0]
                for old, new in (node.config.get("mapping") or {}).items():
                    frames[current_id] = frames[current_id].withColumnRenamed(str(old), str(new))
            elif node.type == "transform.cast":
                frames[current_id] = inputs[0].withColumn(
                    str(node.config["column"]),
                    F.col(str(node.config["column"])).cast(str(node.config["dataType"])),
                )
            elif node.type == "transform.union":
                frames[current_id] = inputs[0].unionByName(inputs[1])
            elif node.type == "transform.join":
                if len(inputs) != 2:
                    raise ValueError("Spark Row Trace join requires two inputs")
                condition = str(node.config.get("condition", "")).replace("==", "=")
                if not condition.strip():
                    raise ValueError("Spark Row Trace join requires a condition")
                joined = (
                    inputs[0]
                    .alias("left")
                    .join(inputs[1].alias("right"), F.expr(condition), "inner")
                )
                left_columns = inputs[0].columns
                frames[current_id] = joined.select(
                    *[F.col(f"left.{column}").alias(column) for column in left_columns],
                    *[
                        F.col(f"right.{column}").alias(
                            column if column not in left_columns else f"right_{column}"
                        )
                        for column in inputs[1].columns
                    ],
                )
            elif node.type == "transform.aggregate":
                group_by = [str(value) for value in node.config.get("groupBy", [])]
                grouped = inputs[0].groupBy(*[F.col(column) for column in group_by])
                aggregations = node.config.get("aggregations", []) or [
                    {"expression": "count(*)", "alias": "row_count"}
                ]
                aggregate_exprs = [
                    F.expr(str(item.get("expression", "count(*)"))).alias(
                        str(item.get("alias", "value"))
                    )
                    for item in aggregations
                ]
                frames[current_id] = grouped.agg(*aggregate_exprs)
            elif node.type == "transform.explode":
                column = str(node.config["column"])
                frames[current_id] = inputs[0].withColumn(column, F.explode_outer(F.col(column)))
            elif node.type.startswith("dataset.") or node.type.startswith("sink."):
                frames[current_id] = inputs[0]
            else:
                raise ValueError(f"Spark Row Trace does not support {node.type}")
            sampled = [
                row.asDict(recursive=True) for row in frames[current_id].limit(max_rows).collect()
            ]
            snapshots.append({"node_id": current_id, "type": node.type, "rows": sampled})
            if current_id == node_id:
                break
        return {
            "ok": True,
            "trace_mode": "spark_subgraph",
            "execution_backed": True,
            "provenance": "spark_dataframe_subgraph",
            "node_id": node_id,
            "rows": snapshots[-1]["rows"] if snapshots else [],
            "steps": snapshots,
            "unsupported": [],
        }
    finally:
        spark.stop()


def summarize_spark_events(
    events: Iterable[dict[str, Any]],
    *,
    moderate_skew_ratio: float = 2.0,
    severe_skew_ratio: float = 5.0,
) -> dict[str, Any]:
    if not 1.0 <= moderate_skew_ratio < severe_skew_ratio:
        raise ValueError("Skew thresholds must satisfy 1 <= moderate < severe")
    stages: dict[int, dict[str, Any]] = defaultdict(lambda: {"tasks": [], "name": ""})
    for event in events:
        kind = event.get("Event")
        if kind == "SparkListenerStageSubmitted":
            info = event.get("Stage Info", {})
            stage_id = int(info.get("Stage ID", -1))
            stages[stage_id]["name"] = info.get("Stage Name", "")
        elif kind == "SparkListenerTaskEnd":
            stage_id = int(event.get("Stage ID", -1))
            metrics = event.get("Task Metrics", {}) or {}
            task_info = event.get("Task Info", {}) or {}
            stages[stage_id]["tasks"].append(
                {
                    "duration_ms": max(
                        0,
                        int(task_info.get("Finish Time", 0)) - int(task_info.get("Launch Time", 0)),
                    ),
                    "executor_run_time_ms": int(metrics.get("Executor Run Time", 0) or 0),
                    "shuffle_read_bytes": int(
                        (metrics.get("Shuffle Read Metrics", {}) or {}).get("Remote Bytes Read", 0)
                        or 0
                    )
                    + int(
                        (metrics.get("Shuffle Read Metrics", {}) or {}).get("Local Bytes Read", 0)
                        or 0
                    ),
                    "shuffle_write_bytes": int(
                        (metrics.get("Shuffle Write Metrics", {}) or {}).get(
                            "Shuffle Bytes Written", 0
                        )
                        or 0
                    ),
                    "input_bytes": int(
                        (metrics.get("Input Metrics", {}) or {}).get("Bytes Read", 0) or 0
                    ),
                    "output_bytes": int(
                        (metrics.get("Output Metrics", {}) or {}).get("Bytes Written", 0) or 0
                    ),
                    "memory_bytes_spilled": int(metrics.get("Memory Bytes Spilled", 0) or 0),
                    "disk_bytes_spilled": int(metrics.get("Disk Bytes Spilled", 0) or 0),
                    "executor_cpu_time_ns": int(metrics.get("Executor CPU Time", 0) or 0),
                }
            )

    summaries = []
    for stage_id, data in sorted(stages.items()):
        durations = [t["duration_ms"] for t in data["tasks"]]
        med = median(durations) if durations else 0
        mx = max(durations) if durations else 0
        ordered = sorted(durations)
        p95 = ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)] if ordered else 0
        skew = round(mx / med, 2) if med else 0
        summaries.append(
            {
                "stage_id": stage_id,
                "name": data["name"],
                "task_count": len(durations),
                "median_task_ms": med,
                "max_task_ms": mx,
                "p95_task_ms": p95,
                "skew_score": skew,
                "shuffle_read_bytes": sum(t["shuffle_read_bytes"] for t in data["tasks"]),
                "shuffle_write_bytes": sum(t["shuffle_write_bytes"] for t in data["tasks"]),
                "input_bytes": sum(t["input_bytes"] for t in data["tasks"]),
                "output_bytes": sum(t["output_bytes"] for t in data["tasks"]),
                "memory_bytes_spilled": sum(t["memory_bytes_spilled"] for t in data["tasks"]),
                "disk_bytes_spilled": sum(t["disk_bytes_spilled"] for t in data["tasks"]),
                "executor_cpu_time_ns": sum(t["executor_cpu_time_ns"] for t in data["tasks"]),
                "scheduler_delay_ms": sum(
                    max(0, t["duration_ms"] - t["executor_run_time_ms"]) for t in data["tasks"]
                ),
                "diagnostic": "severe skew"
                if skew >= severe_skew_ratio
                else "moderate skew"
                if skew >= moderate_skew_ratio
                else "balanced/unknown",
            }
        )
    return {"stages": summaries}


def summarize_spark_event_stream(
    events: Iterable[dict[str, Any]],
    *,
    moderate_skew_ratio: float = 2.0,
    severe_skew_ratio: float = 5.0,
    max_tasks_per_stage: int = 10_000,
) -> dict[str, Any]:
    """Summarize an event iterator without retaining the complete event log.

    Spark task metrics are retained in a bounded reservoir per stage. This keeps
    skew/percentile diagnostics useful while making memory use independent of the
    total event-log size.
    """
    if max_tasks_per_stage < 1:
        raise ValueError("max_tasks_per_stage must be positive")
    staged: dict[int, deque[dict[str, Any]]] = defaultdict(
        lambda: deque(maxlen=max_tasks_per_stage)
    )
    names: dict[int, str] = {}
    for event in events:
        kind = event.get("Event")
        if kind == "SparkListenerStageSubmitted":
            info = event.get("Stage Info", {}) or {}
            stage_id = int(info.get("Stage ID", -1))
            names[stage_id] = str(info.get("Stage Name", ""))
        elif kind == "SparkListenerTaskEnd":
            stage_id = int(event.get("Stage ID", -1))
            metrics = event.get("Task Metrics", {}) or {}
            task_info = event.get("Task Info", {}) or {}
            staged[stage_id].append(
                {
                    "duration_ms": max(
                        0,
                        int(task_info.get("Finish Time", 0)) - int(task_info.get("Launch Time", 0)),
                    ),
                    "executor_run_time_ms": int(metrics.get("Executor Run Time", 0) or 0),
                    "shuffle_read_bytes": int(
                        (metrics.get("Shuffle Read Metrics", {}) or {}).get("Remote Bytes Read", 0)
                        or 0
                    )
                    + int(
                        (metrics.get("Shuffle Read Metrics", {}) or {}).get("Local Bytes Read", 0)
                        or 0
                    ),
                    "shuffle_write_bytes": int(
                        (metrics.get("Shuffle Write Metrics", {}) or {}).get(
                            "Shuffle Bytes Written", 0
                        )
                        or 0
                    ),
                    "input_bytes": int(
                        (metrics.get("Input Metrics", {}) or {}).get("Bytes Read", 0) or 0
                    ),
                    "output_bytes": int(
                        (metrics.get("Output Metrics", {}) or {}).get("Bytes Written", 0) or 0
                    ),
                    "memory_bytes_spilled": int(metrics.get("Memory Bytes Spilled", 0) or 0),
                    "disk_bytes_spilled": int(metrics.get("Disk Bytes Spilled", 0) or 0),
                    "executor_cpu_time_ns": int(metrics.get("Executor CPU Time", 0) or 0),
                }
            )
    synthetic: list[dict[str, Any]] = []
    for stage_id, tasks in staged.items():
        synthetic.append(
            {
                "Event": "SparkListenerStageSubmitted",
                "Stage Info": {"Stage ID": stage_id, "Stage Name": names.get(stage_id, "")},
            }
        )
        for task in tasks:
            synthetic.append(
                {
                    "Event": "SparkListenerTaskEnd",
                    "Stage ID": stage_id,
                    "Task Info": {"Launch Time": 0, "Finish Time": task["duration_ms"]},
                    "Task Metrics": {
                        "Executor Run Time": task["executor_run_time_ms"],
                        "Shuffle Read Metrics": {
                            "Remote Bytes Read": task["shuffle_read_bytes"],
                            "Local Bytes Read": 0,
                        },
                        "Shuffle Write Metrics": {
                            "Shuffle Bytes Written": task["shuffle_write_bytes"]
                        },
                        "Input Metrics": {"Bytes Read": task["input_bytes"]},
                        "Output Metrics": {"Bytes Written": task["output_bytes"]},
                        "Memory Bytes Spilled": task["memory_bytes_spilled"],
                        "Disk Bytes Spilled": task["disk_bytes_spilled"],
                        "Executor CPU Time": task["executor_cpu_time_ns"],
                    },
                }
            )
    return summarize_spark_events(
        synthetic, moderate_skew_ratio=moderate_skew_ratio, severe_skew_ratio=severe_skew_ratio
    )


def summarize_streaming_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract bounded streaming progress, state, watermark, and checkpoint diagnostics."""
    queries: dict[str, dict[str, Any]] = {}
    checkpoints: set[str] = set()
    for event in events:
        kind = str(event.get("Event") or event.get("event") or "")
        if kind in {"SparkListenerStreamingQueryProgress", "query_progress"}:
            progress = event.get("progress", event)
            query_id = str(progress.get("id") or progress.get("runId") or "unknown")
            state = queries.setdefault(query_id, {"query_id": query_id, "progress": []})
            watermark = (progress.get("eventTime", {}) or {}).get("watermark")
            state_rows = []
            for item in progress.get("stateOperators", []) or []:
                if isinstance(item, dict):
                    state_rows.append(
                        {
                            "operator": item.get("operatorName"),
                            "num_rows_total": item.get("numRowsTotal"),
                            "memory_used_bytes": item.get("memoryUsedBytes"),
                            "num_rows_updated": item.get("numRowsUpdated"),
                        }
                    )
            state["progress"].append(
                {
                    "timestamp": progress.get("timestamp"),
                    "batch_id": progress.get("batchId"),
                    "input_rows_per_second": progress.get("inputRowsPerSecond"),
                    "processed_rows_per_second": progress.get("processedRowsPerSecond"),
                    "num_input_rows": progress.get("numInputRows"),
                    "watermark": watermark,
                    "state_operators": state_rows,
                }
            )
        for key in ("checkpointLocation", "checkpoint_path", "checkpointPath"):
            value = event.get(key)
            if isinstance(value, str) and value:
                checkpoints.add(value)
    for value in queries.values():
        value["progress"].sort(
            key=lambda item: (str(item.get("timestamp")), str(item.get("batch_id")))
        )
        value["latest"] = value["progress"][-1] if value["progress"] else None
    return {
        "queries": [queries[key] for key in sorted(queries)],
        "checkpoint_paths": sorted(checkpoints),
        "query_count": len(queries),
    }


def semantic_graph_diff(left: PipelineDocument, right: PipelineDocument) -> dict[str, Any]:
    left_nodes = {n.id: n for n in left.nodes}
    right_nodes = {n.id: n for n in right.nodes}
    added = sorted(set(right_nodes) - set(left_nodes))
    removed = sorted(set(left_nodes) - set(right_nodes))
    changed = []
    for node_id in sorted(set(left_nodes) & set(right_nodes)):
        a, b = left_nodes[node_id], right_nodes[node_id]
        config_changed = a.config != b.config or a.type != b.type
        position_changed = a.position != b.position
        if config_changed or position_changed:
            changed.append(
                {
                    "node_id": node_id,
                    "type_before": a.type,
                    "type_after": b.type,
                    "config_changed": config_changed,
                    "position_changed": position_changed,
                    "config_before": a.config if config_changed else None,
                    "config_after": b.config if config_changed else None,
                }
            )

    def edge_key(e) -> tuple[str, str, str, str]:
        return (e.from_.node, e.from_.port, e.to.node, e.to.port)

    left_edges = {edge_key(e) for e in left.edges}
    right_edges = {edge_key(e) for e in right.edges}
    return {
        "added_nodes": [right_nodes[n].model_dump() for n in added],
        "removed_nodes": [left_nodes[n].model_dump() for n in removed],
        "changed_nodes": changed,
        "added_edges": [list(e) for e in sorted(right_edges - left_edges)],
        "removed_edges": [list(e) for e in sorted(left_edges - right_edges)],
        "summary": {
            "added_nodes": len(added),
            "removed_nodes": len(removed),
            "changed_nodes": len(changed),
            "added_edges": len(right_edges - left_edges),
            "removed_edges": len(left_edges - right_edges),
        },
    }


def schema_fingerprint(schema: dict[str, Any] | list[dict[str, Any]]) -> str:
    if isinstance(schema, list):
        schema = sorted(schema, key=lambda field: str(field.get("name", "")))
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schema_diff(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    left_by_name = {str(field.get("name")): field for field in left}
    right_by_name = {str(field.get("name")): field for field in right}
    added = sorted(set(right_by_name) - set(left_by_name))
    removed = sorted(set(left_by_name) - set(right_by_name))
    changed = []
    for name in sorted(set(left_by_name) & set(right_by_name)):
        before, after = left_by_name[name], right_by_name[name]
        if before != after:
            changed.append({"name": name, "before": before, "after": after})

    def flatten(fields: list[dict[str, Any]], prefix: str = "") -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for field in fields:
            name = str(field.get("name", ""))
            path = f"{prefix}.{name}" if prefix else name
            result[path] = field
            nested = field.get("fields")
            if isinstance(nested, list):
                result.update(flatten([item for item in nested if isinstance(item, dict)], path))
        return result

    left_flat, right_flat = flatten(left), flatten(right)
    nested_added = sorted(set(right_flat) - set(left_flat) - set(added))
    nested_removed = sorted(set(left_flat) - set(right_flat) - set(removed))
    nested_changed = [
        {
            "path": path,
            "before": left_flat[path],
            "after": right_flat[path],
        }
        for path in sorted(set(left_flat) & set(right_flat))
        if "." in path and left_flat[path] != right_flat[path]
    ]
    incompatible_types = any(
        isinstance(item.get("before"), dict)
        and isinstance(item.get("after"), dict)
        and cast(dict[str, Any], item["before"]).get("type")
        != cast(dict[str, Any], item["after"]).get("type")
        for item in changed + nested_changed
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "nested_added": nested_added,
        "nested_removed": nested_removed,
        "nested_changed": nested_changed,
        "compatible": not removed and not nested_removed and not incompatible_types,
    }


def evaluate_schema_contract(
    diff: dict[str, Any], *, mode: str = "block", allow_added: bool = True
) -> dict[str, Any]:
    """Apply a deterministic warn/block policy to a schema diff."""
    if mode not in {"warn", "block"}:
        raise ValueError("Schema contract mode must be 'warn' or 'block'")
    breaking: list[dict[str, Any]] = []
    if not allow_added:
        breaking.extend({"kind": "added", "name": name} for name in diff.get("added", []))
        breaking.extend(
            {"kind": "nested_added", "path": path} for path in diff.get("nested_added", [])
        )
    breaking.extend({"kind": "removed", "name": name} for name in diff.get("removed", []))
    breaking.extend(
        {"kind": "nested_removed", "path": path} for path in diff.get("nested_removed", [])
    )
    breaking.extend(
        {"kind": "type_changed", **item}
        for item in diff.get("changed", [])
        if item.get("before", {}).get("type") != item.get("after", {}).get("type")
    )
    breaking.extend(
        {"kind": "nested_type_changed", **item}
        for item in diff.get("nested_changed", [])
        if item.get("before", {}).get("type") != item.get("after", {}).get("type")
    )
    return {
        "mode": mode,
        "status": "blocked" if breaking and mode == "block" else "warned" if breaking else "passed",
        "breaking": breaking,
        "compatible": not breaking,
    }


def profile_rows(
    rows: list[dict[str, Any]],
    *,
    include_sensitive_metrics: bool = True,
    max_rows: int = 200,
    max_columns: int = 100,
    top_values: int = 5,
) -> dict[str, Any]:
    """Profile bounded rows with explicit sampling and output limits."""
    if (
        max_rows < 1
        or max_rows > 100_000
        or max_columns < 1
        or max_columns > 1_000
        or top_values < 0
        or top_values > 100
    ):
        raise ValueError("profile limits are outside the supported safety bounds")
    bounded_rows = rows[:max_rows]
    columns = sorted({key for row in bounded_rows for key in row})[:max_columns]
    profile: dict[str, Any] = {}
    for column in columns:
        values = [row.get(column) for row in bounded_rows]
        present = [value for value in values if value is not None]
        item: dict[str, Any] = {
            "count": len(values),
            "null_count": len(values) - len(present),
            "distinct_count": len({repr(value) for value in present}),
        }
        numeric = [
            value
            for value in present
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        if numeric and include_sensitive_metrics:
            item["min"] = min(numeric)
            item["max"] = max(numeric)
            item["mean"] = mean(numeric)
            item["stddev"] = pstdev(numeric)
        if present and not numeric and include_sensitive_metrics:
            counts: dict[str, int] = defaultdict(int)
            for value in present:
                counts[repr(value)] += 1
            item["top_values"] = [
                {"value": value, "count": count}
                for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[
                    :top_values
                ]
            ]
        profile[column] = item
    return {
        "row_count": len(bounded_rows),
        "columns": profile,
        "limits": {"max_rows": max_rows, "max_columns": max_columns, "top_values": top_values},
    }


def profile_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare profile snapshots while marking unreliable metrics explicitly."""
    before_columns: dict[str, dict[str, Any]] = (
        before["columns"] if isinstance(before.get("columns"), dict) else {}
    )
    after_columns: dict[str, dict[str, Any]] = (
        after["columns"] if isinstance(after.get("columns"), dict) else {}
    )
    names = sorted(set(before_columns) | set(after_columns))
    changes: dict[str, Any] = {}
    insufficient = not isinstance(before.get("row_count"), int) or not isinstance(
        after.get("row_count"), int
    )
    for name in names:
        left = before_columns.get(name)
        right = after_columns.get(name)
        if not isinstance(left, dict) or not isinstance(right, dict):
            changes[name] = {"status": "insufficient_data", "reason": "column_added_or_removed"}
            insufficient = True
            continue
        metrics: dict[str, Any] = {}
        for metric in ("count", "null_count", "distinct_count", "min", "max"):
            old, new = left.get(metric), right.get(metric)
            valid = all(
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in (old, new)
            )
            if not valid:
                metrics[metric] = {"status": "insufficient_data"}
                insufficient = True
                continue
            numeric_old = float(cast(int | float, old))
            numeric_new = float(cast(int | float, new))
            delta = numeric_new - numeric_old
            metrics[metric] = {
                "before": old,
                "after": new,
                "delta": delta,
                "relative_delta": None if numeric_old == 0 else delta / numeric_old,
            }
        changes[name] = {"status": "ok", "metrics": metrics}
    return {
        "status": "insufficient_data" if insufficient else "ok",
        "before_row_count": before.get("row_count"),
        "after_row_count": after.get("row_count"),
        "added_columns": sorted(set(after_columns) - set(before_columns)),
        "removed_columns": sorted(set(before_columns) - set(after_columns)),
        "columns": changes,
    }
