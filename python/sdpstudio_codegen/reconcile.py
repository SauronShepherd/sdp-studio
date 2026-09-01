from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import cast

import sqlglot
from sdpstudio_core.models import PipelineDocument
from sqlglot import exp


@dataclass(frozen=True)
class ReconcileProblem:
    code: str
    message: str
    file: str = "transformations/generated.py"
    line: int | None = None


@dataclass(frozen=True)
class ReconcileResult:
    document: PipelineDocument
    changed: bool
    ownership: str
    problems: tuple[ReconcileProblem, ...] = ()
    regions: tuple[OwnershipRegion, ...] = ()


@dataclass(frozen=True)
class OwnershipRegion:
    start_line: int
    end_line: int
    ownership: str
    node_id: str | None = None


_OWNERSHIP_REGION = re.compile(
    r"^\s*#\s*sdpstudio:region\s+node=(?P<node>[^\s]+)\s+ownership=(?P<ownership>visual|custom)\s*$"
)


def parse_ownership_markers(source: str) -> tuple[OwnershipRegion, ...]:
    """Read deterministic Studio ownership boundaries without executing source."""
    regions: list[OwnershipRegion] = []
    open_region: tuple[int, str, str] | None = None
    for line_number, line in enumerate(source.splitlines(), start=1):
        match = _OWNERSHIP_REGION.match(line)
        if match:
            open_region = (line_number, match.group("node"), match.group("ownership"))
        elif open_region and line.strip() == "# sdpstudio:endregion":
            start, node_id, ownership = open_region
            regions.append(OwnershipRegion(start, line_number, ownership, node_id))
            open_region = None
    return tuple(regions)


def reconcile_python(document: PipelineDocument, source: str) -> ReconcileResult:
    """Safely reconcile the supported generated Python subset.

    The original document is returned unchanged when parsing or structural
    matching fails. Unsupported edits are explicitly reported as code-owned;
    they are never silently overwritten.
    """
    try:
        tree = ast.parse(source, filename="transformations/generated.py")
    except SyntaxError as exc:
        return ReconcileResult(
            document,
            False,
            "custom",
            (
                ReconcileProblem(
                    "SDPS-RECON-001", "Python syntax is not supported", line=exc.lineno
                ),
            ),
            (OwnershipRegion(exc.lineno or 1, exc.lineno or 1, "custom"),),
        )
    marker_regions = parse_ownership_markers(source)
    outputs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "dp"
            for decorator in node.decorator_list
        )
    ]
    if not outputs and source.strip():
        return ReconcileResult(
            document,
            False,
            "custom",
            (ReconcileProblem("SDPS-RECON-002", "No supported SDP declarations were found"),),
            (OwnershipRegion(1, max(1, len(source.splitlines())), "custom"),),
        )
    if len(outputs) != sum(
        node.type.startswith("dataset.") or node.type == "sink.external" for node in document.nodes
    ):
        return ReconcileResult(
            document,
            False,
            "custom",
            (
                ReconcileProblem(
                    "SDPS-RECON-002", "Generated declarations do not match the visual model"
                ),
            ),
            (OwnershipRegion(1, max(1, len(source.splitlines())), "custom"),),
        )
    nodes = {node.id: node.model_copy(deep=True) for node in document.nodes}
    by_var = {f"n_{node.id.replace('-', '_')}": node for node in nodes.values()}
    problems: list[ReconcileProblem] = []
    regions: list[OwnershipRegion] = []
    for function in outputs:
        for decorator in function.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in {
                "materialized_view",
                "table",
                "temporary_view",
                "append_flow",
                "create_auto_cdc_flow",
            }:
                problems.append(
                    ReconcileProblem(
                        "SDPS-RECON-003", "Unsupported decorator edit", line=decorator.lineno
                    )
                )
                continue
            output = next(
                (n for n in nodes.values() if n.config.get("name") == function.name), None
            )
            if output is not None and (
                decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                output.config["name"] = decorator.args[0].value
            target = next(
                (
                    keyword.value.value
                    for keyword in decorator.keywords
                    if keyword.arg == "target"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ),
                None,
            )
            output = output or next(
                (n for n in nodes.values() if n.config.get("name") == target), None
            )
            if output is not None and decorator.func.attr == "create_auto_cdc_flow":
                keys = next(
                    (keyword.value for keyword in decorator.keywords if keyword.arg == "keys"),
                    None,
                )
                if isinstance(keys, (ast.List, ast.Tuple)):
                    key_values = [
                        item.value
                        for item in keys.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    ]
                    if len(key_values) == len(keys.elts):
                        output.config["keys"] = key_values
                sequence = next(
                    (
                        keyword.value
                        for keyword in decorator.keywords
                        if keyword.arg == "sequence_by"
                    ),
                    None,
                )
                if isinstance(sequence, ast.Call) and isinstance(sequence.func, ast.Attribute):
                    sequence_arg = sequence.args[0] if sequence.args else None
                    if (
                        sequence.func.attr == "col"
                        and isinstance(sequence_arg, ast.Constant)
                        and isinstance(sequence_arg.value, str)
                    ):
                        output.config["sequence_by"] = sequence_arg.value
        for statement in function.body:
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Name)
                and statement.value.func.id == "_sdpstudio_capture_plan"
            ):
                # Deterministic runtime instrumentation emitted by Studio is
                # not user-owned transformation code.
                continue
            if (
                not isinstance(statement, ast.Assign)
                or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name)
            ):
                if isinstance(statement, ast.Return):
                    continue
                problems.append(
                    ReconcileProblem(
                        "SDPS-RECON-003",
                        "Unsupported code edit was preserved as code-owned",
                        line=statement.lineno,
                    )
                )
                regions.append(
                    OwnershipRegion(
                        statement.lineno,
                        getattr(statement, "end_lineno", statement.lineno),
                        "custom",
                    )
                )
                continue
            node = by_var.get(statement.targets[0].id)
            value = statement.value
            if node is None:
                continue
            if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
                problems.append(
                    ReconcileProblem(
                        "SDPS-RECON-003",
                        "Unsupported transformation edit was preserved as code-owned",
                        line=statement.lineno,
                    )
                )
                regions.append(
                    OwnershipRegion(
                        statement.lineno,
                        getattr(statement, "end_lineno", statement.lineno),
                        "custom",
                        node.id,
                    )
                )
                continue
            supported = False
            if (
                value.func.attr == "table"
                and value.args
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                node.config["table"] = value.args[0].value
                supported = True
            elif (
                value.func.attr == "withColumn"
                and len(value.args) == 2
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                expression = value.args[1]
                if (
                    isinstance(expression, ast.Call)
                    and isinstance(expression.func, ast.Attribute)
                    and expression.func.attr == "expr"
                    and expression.args
                    and isinstance(expression.args[0], ast.Constant)
                    and isinstance(expression.args[0].value, str)
                ):
                    node.config.update(
                        {"name": value.args[0].value, "expression": expression.args[0].value}
                    )
                    supported = True
            elif (
                value.func.attr == "withColumnRenamed"
                and len(value.args) == 2
                and all(
                    isinstance(item, ast.Constant) and isinstance(item.value, str)
                    for item in value.args
                )
            ):
                mapping = dict(node.config.get("mapping") or {})
                mapping[cast(ast.Constant, value.args[0]).value] = cast(
                    ast.Constant, value.args[1]
                ).value
                node.config["mapping"] = mapping
                supported = True
            elif value.func.attr == "cast" and isinstance(value.func.value, ast.Call):
                column = value.func.value
                if (
                    getattr(column.func, "attr", None) == "col"
                    and column.args
                    and isinstance(column.args[0], ast.Constant)
                    and value.args
                    and isinstance(value.args[0], ast.Constant)
                    and isinstance(column.args[0].value, str)
                    and isinstance(value.args[0].value, str)
                ):
                    node.config.update(
                        {"column": column.args[0].value, "dataType": value.args[0].value}
                    )
                    supported = True
            elif value.func.attr == "distinct" and not value.args:
                supported = True
            elif (
                value.func.attr == "drop"
                and value.args
                and all(
                    isinstance(item, ast.Constant) and isinstance(item.value, str)
                    for item in value.args
                )
            ):
                node.config["columns"] = [cast(ast.Constant, item).value for item in value.args]
                supported = True
            elif (
                value.func.attr == "limit"
                and len(value.args) == 1
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, int)
            ):
                node.config["count"] = value.args[0].value
                supported = True
            elif value.func.attr == "filter" and value.args and isinstance(value.args[0], ast.Call):
                arg = value.args[0]
                if (
                    isinstance(arg.func, ast.Attribute)
                    and arg.func.attr == "expr"
                    and arg.args
                    and isinstance(arg.args[0], ast.Constant)
                    and isinstance(arg.args[0].value, str)
                ):
                    node.config["expression"] = arg.args[0].value
                    supported = True
                else:
                    problems.append(
                        ReconcileProblem(
                            "SDPS-RECON-003",
                            "Unsupported filter edit was preserved as code-owned",
                            line=statement.lineno,
                        )
                    )
                    regions.append(
                        OwnershipRegion(
                            statement.lineno,
                            getattr(statement, "end_lineno", statement.lineno),
                            "custom",
                            node.id,
                        )
                    )
            elif value.func.attr == "dropDuplicates" and isinstance(value.func.value, ast.Call):
                watermark = value.func.value
                if (
                    isinstance(watermark.func, ast.Attribute)
                    and watermark.func.attr == "withWatermark"
                    and len(watermark.args) == 2
                    and all(
                        isinstance(item, ast.Constant) and isinstance(item.value, str)
                        for item in watermark.args
                    )
                ):
                    values = (
                        value.args[0].elts
                        if len(value.args) == 1 and isinstance(value.args[0], ast.List)
                        else value.args
                    )
                    if values and all(
                        isinstance(item, ast.Constant) and isinstance(item.value, str)
                        for item in values
                    ):
                        node.config.update(
                            {
                                "eventTime": cast(ast.Constant, watermark.args[0]).value,
                                "watermark": cast(ast.Constant, watermark.args[1]).value,
                                "columns": [cast(ast.Constant, item).value for item in values],
                            }
                        )
                        supported = True
            elif value.func.attr in {"select", "dropDuplicates"}:
                values = (
                    value.args[0].elts
                    if len(value.args) == 1 and isinstance(value.args[0], ast.List)
                    else value.args
                )
                columns: list[str] = []
                for item in values:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        columns.append(item.value)
                    elif (
                        isinstance(item, ast.Call)
                        and isinstance(item.func, ast.Attribute)
                        and item.func.attr == "expr"
                        and item.args
                        and isinstance(item.args[0], ast.Constant)
                        and isinstance(item.args[0].value, str)
                    ):
                        columns.append(item.args[0].value)
                if values and len(columns) == len(values):
                    node.config["columns"] = columns
                    supported = True
            if supported:
                regions.append(
                    OwnershipRegion(
                        statement.lineno,
                        getattr(statement, "end_lineno", statement.lineno),
                        "visual",
                        node.id,
                    )
                )
    if problems:
        return ReconcileResult(document, False, "custom", tuple(problems), tuple(regions))
    updated = document.model_copy(update={"nodes": list(nodes.values())})
    return ReconcileResult(
        updated, updated != document, "visual", (), tuple(marker_regions or regions)
    )


def reconcile_sql(document: PipelineDocument, source: str) -> ReconcileResult:
    """Reconcile the deliberately small, generated SQL subset.

    Only unambiguous source-table and filter predicates are visual-owned. Any
    other SQL shape remains custom-owned and never overwrites the graph.
    """
    try:
        tree = sqlglot.parse_one(source, read="spark")
    except Exception as exc:
        return ReconcileResult(
            document,
            False,
            "custom",
            (
                ReconcileProblem(
                    "SDPS-RECON-101",
                    "SQL syntax is not supported: " + str(exc),
                    file="transformations/generated.sql",
                ),
            ),
            (OwnershipRegion(1, max(1, len(source.splitlines())), "custom"),),
        )
    nodes = {node.id: node.model_copy(deep=True) for node in document.nodes}
    sources = [node for node in nodes.values() if node.type == "source.table"]
    filters = [node for node in nodes.values() if node.type == "transform.filter"]
    tables = list(tree.find_all(exp.Table))
    output_names = {
        str(node.config.get("name", ""))
        for node in nodes.values()
        if node.type.startswith("dataset.")
    }
    source_tables = [table for table in tables if table.name not in output_names]
    wheres = list(tree.find_all(exp.Where))
    limits = list(tree.find_all(exp.Limit))
    limit_nodes = [node for node in nodes.values() if node.type == "transform.limit"]
    regions: list[OwnershipRegion] = []
    problems: list[ReconcileProblem] = []
    if len(sources) == 1 and len(source_tables) == 1:
        table = source_tables[0]
        nodes[sources[0].id].config["table"] = table.sql(dialect="spark")
        regions.append(
            OwnershipRegion(1, max(1, len(source.splitlines())), "visual", sources[0].id)
        )
    elif sources:
        problems.append(
            ReconcileProblem(
                "SDPS-RECON-102",
                "SQL source tables are ambiguous",
                file="transformations/generated.sql",
            )
        )
    if len(filters) == 1 and len(wheres) == 1:
        nodes[filters[0].id].config["expression"] = wheres[0].this.sql(dialect="spark")
        regions.append(
            OwnershipRegion(1, max(1, len(source.splitlines())), "visual", filters[0].id)
        )
    elif filters:
        problems.append(
            ReconcileProblem(
                "SDPS-RECON-103",
                "SQL filter predicates are ambiguous",
                file="transformations/generated.sql",
            )
        )
    if (
        len(limit_nodes) == 1
        and len(limits) == 1
        and isinstance(limits[0].expression, exp.Literal)
        and limits[0].expression.is_int
    ):
        nodes[limit_nodes[0].id].config["count"] = int(limits[0].expression.this)
        regions.append(
            OwnershipRegion(1, max(1, len(source.splitlines())), "visual", limit_nodes[0].id)
        )
    elif limit_nodes:
        problems.append(
            ReconcileProblem(
                "SDPS-RECON-105",
                "SQL limit clauses are ambiguous",
                file="transformations/generated.sql",
            )
        )
    if problems or not regions:
        if not problems:
            problems.append(
                ReconcileProblem(
                    "SDPS-RECON-104",
                    "SQL shape is not supported for visual reconciliation",
                    file="transformations/generated.sql",
                )
            )
        return ReconcileResult(
            document,
            False,
            "custom",
            tuple(problems),
            (OwnershipRegion(1, max(1, len(source.splitlines())), "custom"),),
        )
    updated = document.model_copy(update={"nodes": list(nodes.values())})
    return ReconcileResult(updated, updated != document, "visual", (), tuple(regions))
