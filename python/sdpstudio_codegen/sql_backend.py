from __future__ import annotations

import hashlib
import re

import sqlglot
from sdpstudio_core.graph import GraphIndex, has_errors
from sdpstudio_core.ir import lower_pipeline
from sdpstudio_core.models import (
    GeneratedFile,
    GenerationResult,
    PipelineDocument,
    Problem,
    SourceRange,
)
from sqlglot import exp
from sqlglot.errors import ParseError


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _ident(value: str) -> str:
    value = re.sub(r"\W+", "_", value).strip("_") or "dataset"
    return value if not value[0].isdigit() else f"dataset_{value}"


def _parse_sql(expression: str) -> str:
    """Validate generated SQL through SQLGlot before it reaches a runtime."""
    try:
        sqlglot.parse_one(expression, read="spark")
    except ParseError as exc:
        raise ValueError(f"Generated SQL is invalid: {exc}") from exc
    return expression


def _query(
    parent: str,
    expressions: list[str] | tuple[str, ...] = ("*",),
    *,
    where: str | None = None,
    distinct: bool = False,
    limit: int | None = None,
) -> str:
    """Build a Spark SQL query through SQLGlot's expression tree."""
    source = sqlglot.parse_one(parent, read="spark")
    # Parse every projection/predicate before attaching it to the AST. This
    # keeps SQL construction dialect-aware and reserves raw SQL for explicit
    # source/query blocks.
    projection_nodes = [sqlglot.parse_one(expression, read="spark") for expression in expressions]
    query = exp.select(*projection_nodes).from_(exp.Subquery(this=source, alias="input"))
    if distinct:
        query = query.distinct()
    if where:
        query = query.where(sqlglot.parse_one(where, read="spark"))
    if limit is not None:
        query = query.limit(limit)
    return query.sql(dialect="spark")


def _source(node) -> str:
    if node.type in {"utility.constant", "utility.parameter"}:
        name = str(node.config.get("name", "value"))
        value = node.config.get("value", node.config.get("default", ""))
        literal = f"'{value}'" if isinstance(value, str) else str(value)
        return f"SELECT {literal} AS {name}"
    if node.type == "source.table":
        return f"SELECT * FROM {node.config.get('table', '')}"
    if node.type == "source.sql_query":
        return str(node.config.get("query", ""))
    if node.type == "utility.component_input":
        return f"SELECT * FROM {node.config.get('name', node.id)}"
    raise ValueError(f"SQL backend does not support {node.type}")


def _transform(node, parent: str) -> str:
    config = node.config
    if node.type == "utility.custom_code":
        raise ValueError("Custom code requires an explicit owned source block; generation stopped")
    if node.type in {"utility.group", "utility.note", "utility.component_output"}:
        return parent
    if node.type.startswith("quality."):
        # Preserve quality checks in generated SQL as deterministic metadata.
        # Execution remains runtime-owned; no implicit actions or writes occur.
        return f"/* SDP Studio quality: {node.type} {config!r} */\n{parent}"
    if node.type == "transform.filter":
        return _query(parent, where=str(config.get("expression", "")))
    if node.type == "transform.select":
        columns = [str(x) for x in config.get("columns") or ["*"]]
        return _query(parent, columns)
    if node.type == "transform.derive":
        return f"SELECT input.*, {config.get('expression', '')} AS {config.get('name', 'derived')} FROM ({parent}) AS input"
    if node.type == "transform.sql_project":
        query = str(config.get("query", "")).strip()
        if not query:
            raise ValueError("transform.sql_project requires query")
        return f"SELECT {query} FROM ({parent}) AS input"
    if node.type == "transform.drop":
        raise ValueError("SQL generation requires explicit select columns for drop")
    if node.type == "transform.distinct":
        return _query(parent, distinct=True)
    if node.type == "transform.deduplicate_event_time":
        columns = [str(value) for value in config.get("columns") or []]
        event_time = str(config.get("eventTime", "event_time"))
        if not columns:
            raise ValueError("deduplicate_event_time requires key columns")
        partition = ", ".join(columns)
        return f"SELECT * FROM (SELECT input.*, ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY {event_time} DESC) AS __sdpstudio_row_number FROM ({parent}) AS input) AS deduplicated WHERE __sdpstudio_row_number = 1"
    if node.type == "transform.reorder":
        columns = [str(value) for value in config.get("columns") or ["*"]]
        return _query(parent, columns)
    if node.type == "transform.replace":
        column = str(config.get("column", ""))
        expression = column
        for old, new in sorted(
            (config.get("mapping") or {}).items(), key=lambda item: str(item[0])
        ):
            expression = f"CASE WHEN {expression} = {old!r} THEN {new!r} ELSE {expression} END"
        return f"SELECT input.*, {expression} AS {column} FROM ({parent}) AS input"
    if node.type == "transform.flatten_struct":
        raise ValueError("SQL generation requires explicit struct fields for flatten_struct")
    if node.type == "transform.build_struct":
        fields = config.get("fields") or {}
        struct_expression = ", ".join(
            f"{value} AS {name}" for name, value in sorted(fields.items())
        )
        return f"SELECT input.*, STRUCT({struct_expression}) AS {config.get('target', 'struct')} FROM ({parent}) AS input"
    if node.type == "transform.build_map":
        pairs = ", ".join(
            f"{key}, {value}"
            for key, value in zip(
                config.get("keys") or [], config.get("values") or [], strict=False
            )
        )
        return f"SELECT input.*, MAP({pairs}) AS {config.get('target', 'map')} FROM ({parent}) AS input"
    if node.type == "transform.build_array":
        array_expression = ", ".join(str(value) for value in config.get("expressions") or [])
        return f"SELECT input.*, ARRAY({array_expression}) AS {config.get('target', 'array')} FROM ({parent}) AS input"
    if node.type == "transform.limit":
        return _query(parent, limit=int(config.get("count", 100)))
    if node.type == "transform.posexplode":
        column = str(config.get("column", ""))
        position = str(config.get("position", "pos"))
        target = str(config.get("target", "item"))
        return (
            f"SELECT input.*, {position}, {target} FROM ({parent}) AS input "
            f"LATERAL VIEW posexplode(input.{column}) exploded AS {position}, {target}"
        )
    if node.type == "transform.aggregate":
        groups = [str(value) for value in config.get("groupBy") or []]
        aggregations = config.get("aggregations") or []
        aggregate_expressions: list[str] = [
            str(item.get("expression", "count(*)")) + f" AS {item.get('alias', 'value')}"
            for item in aggregations
        ]
        select_list = ", ".join(groups + aggregate_expressions) or "count(*) AS row_count"
        group_clause = f" GROUP BY {', '.join(groups)}" if groups else ""
        return f"SELECT {select_list} FROM ({parent}) AS input{group_clause}"
    if node.type in {"transform.intersect", "transform.except"}:
        raise ValueError(f"SQL backend requires binary lowering for {node.type}")
    raise ValueError(f"SQL backend does not support {node.type}")


def _expression(
    index: GraphIndex,
    node_id: str,
    active: set[str] | None = None,
    output_port: str = "out",
) -> str:
    active = active or set()
    if node_id in active:
        raise ValueError("cycle encountered while lowering SQL")
    active = {*active, node_id}
    node = index.nodes[node_id]
    if node.type.startswith("source.") or node.type == "utility.component_input":
        return _source(node)
    parents = {edge.to.port: edge.from_.node for edge in index.incoming.get(node_id, [])}
    if node.type == "transform.join":
        if "left" not in parents or "right" not in parents:
            raise ValueError("join requires left and right inputs")
        left = _expression(index, parents["left"], active, "left")
        right = _expression(index, parents["right"], active, "right")
        how = str(node.config.get("how", "inner")).upper().replace("_", " ")
        if how == "CROSS":
            return f"SELECT * FROM ({left}) AS left_input CROSS JOIN ({right}) AS right_input"
        condition = str(node.config.get("condition", ""))
        return f"SELECT * FROM ({left}) AS left_input {how} JOIN ({right}) AS right_input ON {condition}"
    if node.type in {"transform.intersect", "transform.except"}:
        if "left" not in parents or "right" not in parents:
            raise ValueError(f"{node.type} requires left and right inputs")
        left = _expression(index, parents["left"], active, "left")
        right = _expression(index, parents["right"], active, "right")
        operator = "INTERSECT" if node.type.endswith("intersect") else "EXCEPT"
        return f"({left}) {operator} ({right})"
    if len(parents) != 1:
        raise ValueError(f"SQL backend requires one input for {node.type}")
    parent_edge = next(iter(index.incoming[node_id]))
    parent = _expression(index, parent_edge.from_.node, active, parent_edge.from_.port)
    if node.type == "quality.quarantine_split":
        condition = str(node.config.get("condition", "")).strip().lower()
        column = str(node.config.get("column", ""))
        if condition not in {"not_null", "not null", "non_empty", "not_empty"} or not column:
            raise ValueError("quality.quarantine_split requires a supported condition and column")
        predicate = f"{column} IS NOT NULL AND {column} <> ''"
        if output_port == "quarantine":
            predicate = f"{column} IS NULL OR {column} = ''"
        elif output_port not in {"accepted", "in", "out"}:
            raise ValueError(f"Unsupported quality.quarantine_split output port: {output_port}")
        return _query(parent, where=predicate)
    return _transform(node, parent)


def generate_sql_project(document: PipelineDocument) -> GenerationResult:
    lowered = lower_pipeline(document)
    document = lowered.pipeline.graph_view()
    problems = list(lowered.problems)
    if has_errors(problems):
        return GenerationResult(files=[], source_map=[], problems=problems)
    index = GraphIndex(document)
    for node in document.nodes:
        if node.type != "quality.quarantine_split":
            continue
        condition = str(node.config.get("condition", "")).strip().lower()
        if condition not in {"not_null", "not null", "non_empty", "not_empty"}:
            problems.append(
                Problem(
                    code="SDPS-CODEGEN-003",
                    severity="error",
                    message="quality.quarantine_split supports only not_null/non_empty conditions",
                    node_id=node.id,
                    remediation="Use a supported split condition or keep the node code-owned.",
                )
            )
    if has_errors(problems):
        return GenerationResult(files=[], source_map=[], problems=problems)
    lines = ["-- Generated by SDP Studio; the visual model is the source of truth.", ""]
    mappings: list[SourceRange] = []
    for output_id in index.topological_order():
        output = index.nodes[output_id]
        if not output.type.startswith("dataset."):
            continue
        incoming = index.incoming.get(output_id, [])
        if len(incoming) != 1:
            problems.append(
                Problem(
                    code="SDPS-CODEGEN-001",
                    severity="error",
                    message="SQL backend currently requires one input per output",
                    node_id=output.id,
                )
            )
            continue
        try:
            expression = _parse_sql(
                _expression(index, incoming[0].from_.node, output_port=incoming[0].from_.port)
            )
        except ValueError as exc:
            problems.append(
                Problem(
                    code="SDPS-CODEGEN-001", severity="error", message=str(exc), node_id=output.id
                )
            )
            continue
        name = str(output.config.get("name", "dataset"))
        declaration = {
            "dataset.materialized_view": "MATERIALIZED VIEW",
            "dataset.streaming_table": "STREAMING TABLE",
            "dataset.temporary_view": "TEMPORARY VIEW",
        }.get(output.type, "TEMPORARY VIEW")
        start = len(lines) + 1
        lines.extend(
            [
                f"CREATE OR REPLACE {declaration} {_ident(name)} AS",
                expression.rstrip(";") + ";",
                "",
            ]
        )
        mappings.append(
            SourceRange(
                node_id=output.id,
                file="transformations/generated.sql",
                start_line=start,
                end_line=len(lines) - 1,
            )
        )
    if has_errors(problems):
        return GenerationResult(files=[], source_map=mappings, problems=problems)
    content = "\n".join(lines)
    generated_hash = _hash(content)
    mappings = [
        mapping.model_copy(
            update={
                "object_id": f"node:{mapping.node_id}:definition",
                "start_column": 1,
                "end_column": len(content.splitlines()[mapping.start_line - 1]) + 1,
                "content_hash": generated_hash,
            }
        )
        for mapping in mappings
    ]
    return GenerationResult(
        files=[
            GeneratedFile(
                path="transformations/generated.sql", content=content, sha256=generated_hash
            )
        ],
        source_map=mappings,
        problems=problems,
    )
