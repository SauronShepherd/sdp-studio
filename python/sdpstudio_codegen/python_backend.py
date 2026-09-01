from __future__ import annotations

import hashlib
import keyword
import os
import re
from pathlib import Path
from typing import Any

from sdpstudio_core.graph import GraphIndex, has_errors
from sdpstudio_core.ir import lower_pipeline
from sdpstudio_core.models import (
    GeneratedFile,
    GenerationResult,
    PipelineDocument,
    Problem,
    SourceRange,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _py(value: Any) -> str:
    return repr(value)


def _option_py(value: Any) -> str:
    if isinstance(value, str) and value.startswith("secret://"):
        name = value[len("secret://") :].strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid secret environment reference: {value}")
        return f"os.environ[{name!r}]"
    return repr(str(value))


def _has_secret_ref(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("secret://")
    if isinstance(value, dict):
        return any(_has_secret_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_secret_ref(v) for v in value)
    return False


def _options_dict_py(options: dict[str, Any]) -> str:
    pairs = [f"{str(key)!r}: {_option_py(options[key])}" for key in sorted(options)]
    return "{" + ", ".join(pairs) + "}"


def _is_definition(node: Any) -> bool:
    return node.type.startswith("dataset.") or node.type.startswith("sink.")


def _identifier(value: str) -> str:
    cleaned = re.sub(r"\W+", "_", value.strip())
    if not cleaned:
        cleaned = "dataset"
    if cleaned[0].isdigit() or keyword.iskeyword(cleaned):
        cleaned = "svp_" + cleaned
    return cleaned


def _var(node_id: str, port: str | None = None) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "", node_id)[-8:].lower()
    if port and port != "out":
        suffix += "_" + _identifier(port).lower()
    return "n_" + suffix


def _mode_map(document: PipelineDocument) -> dict[str, str]:
    index = GraphIndex(document)
    modes: dict[str, str] = {}
    for node_id in index.topological_order():
        node = index.nodes[node_id]
        if node.type.startswith("source."):
            modes[node_id] = (
                "streaming"
                if node.type == "source.kafka" or bool(node.config.get("streaming"))
                else "batch"
            )
        else:
            parents = [modes.get(e.from_.node, "batch") for e in index.incoming.get(node_id, [])]
            modes[node_id] = "streaming" if any(p == "streaming" for p in parents) else "batch"
    return modes


def _semantic_problems(document: PipelineDocument) -> list[Problem]:
    modes = _mode_map(document)
    problems: list[Problem] = []
    names: dict[str, str] = {}
    identifiers: dict[str, str] = {}
    for node in document.nodes:
        if node.type == "dataset.materialized_view" and modes.get(node.id) == "streaming":
            problems.append(
                Problem(
                    code="SDPS-SDP-001",
                    severity="error",
                    message="Materialized View cannot be generated from a streaming read in portable SDP mode",
                    node_id=node.id,
                    remediation="Use a Streaming Table output or change the source to batch.",
                )
            )
        if node.type == "dataset.streaming_table" and modes.get(node.id) != "streaming":
            problems.append(
                Problem(
                    code="SDPS-SDP-002",
                    severity="error",
                    message="Streaming Table requires a streaming upstream source",
                    node_id=node.id,
                    remediation="Enable streaming on the source or use Materialized View.",
                )
            )
        if node.type == "sink.external" and modes.get(node.id) != "streaming":
            problems.append(
                Problem(
                    code="SDPS-SDP-003",
                    severity="error",
                    message="External SDP sinks support streaming append flows only",
                    node_id=node.id,
                    remediation="Feed the sink from a streaming source/table.",
                )
            )
        if (
            node.type == "transform.join"
            and node.config.get("how") != "cross"
            and not node.config.get("condition")
        ):
            problems.append(
                Problem(
                    code="SDPS-JOIN-001",
                    severity="error",
                    message="Join condition is required for non-cross joins",
                    node_id=node.id,
                )
            )
        if _is_definition(node):
            name = str(node.config.get("name", ""))
            if name:
                if name in names:
                    problems.append(
                        Problem(
                            code="SDPS-SDP-004",
                            severity="error",
                            message=f"Duplicate pipeline dataset/sink name: {name}",
                            node_id=node.id,
                        )
                    )
                names[name] = node.id
                ident = _identifier(name)
                if ident in identifiers and names.get(name) != identifiers[ident]:
                    problems.append(
                        Problem(
                            code="SDPS-CODEGEN-001",
                            severity="error",
                            message=f"Dataset names collide as Python identifiers: {name}",
                            node_id=node.id,
                            remediation="Choose names that remain distinct after punctuation is normalized.",
                        )
                    )
                identifiers[ident] = node.id
    return problems


def _source_expr(node: Any) -> str:
    cfg = node.config
    if node.type in {"utility.constant", "utility.parameter"}:
        name = str(cfg.get("name", "value"))
        value = cfg.get("value", cfg.get("default", ""))
        return f"spark.range(1).select(F.lit({_py(value)}).alias({_py(name)}))"
    if node.type == "source.table":
        table = cfg.get("table", "")
        if cfg.get("streaming"):
            return f"spark.readStream.table({_py(table)})"
        return f"spark.table({_py(table)})"
    if node.type == "source.file":
        stream = "readStream" if cfg.get("streaming") else "read"
        fmt = cfg.get("format", "parquet")
        expr = f"spark.{stream}.format({_py(fmt)})"
        options = cfg.get("options") or {}
        for key in sorted(options):
            expr += f".option({_py(str(key))}, {_option_py(options[key])})"
        expr += f".load({_option_py(cfg.get('path', ''))})"
        return expr
    if node.type == "source.jdbc":
        expr = f"spark.read.format('jdbc').option('url', {_option_py(cfg.get('url', ''))}).option('dbtable', {_option_py(cfg.get('dbtable', ''))})"
        for key in sorted(cfg.get("options") or {}):
            expr += f".option({_py(str(key))}, {_option_py((cfg.get('options') or {})[key])})"
        return expr + ".load()"
    if node.type == "source.kafka":
        expr = f"spark.readStream.format('kafka').option('kafka.bootstrap.servers', {_option_py(cfg.get('bootstrapServers', ''))}).option('subscribe', {_option_py(cfg.get('subscribe', ''))})"
        for key in sorted(cfg.get("options") or {}):
            expr += f".option({_py(str(key))}, {_option_py((cfg.get('options') or {})[key])})"
        return expr + ".load()"
    if node.type == "source.sql_query":
        return f"spark.sql({_py(cfg.get('query', ''))})"
    if node.type == "source.dataset_reference":
        reader = "readStream" if cfg.get("streaming") else "read"
        return f"spark.{reader}.table({_py(cfg.get('name', ''))})"
    if node.type == "source.generic":
        reader = "readStream" if cfg.get("streaming") else "read"
        expr = f"spark.{reader}.format({_py(cfg.get('format', ''))})"
        for key in sorted(cfg.get("options") or {}):
            expr += f".option({_py(str(key))}, {_option_py((cfg.get('options') or {})[key])})"
        return expr + ".load()"
    if node.type == "source.custom_pyspark":
        code = str(cfg.get("code", "")).strip()
        if not code:
            raise ValueError("source.custom_pyspark requires code")
        return code
    if node.type == "utility.component_input":
        return f"spark.table({_py(cfg.get('name', node.id))})"
    raise ValueError(f"unsupported source {node.type}")


def _transform_expr(node: Any, parents: dict[str, str]) -> str:
    cfg = node.config
    if node.type == "utility.custom_code":
        code = str(cfg.get("code", "")).strip()
        parent = parents.get("in") or next(iter(parents.values()), "spark.range(0)")
        expression = code.removeprefix("return ").strip() if code.startswith("return ") else code
        if not expression or "\n" in expression or expression.startswith("return"):
            raise ValueError("Custom code must be a single expression or 'return <expression>'")
        # Keep the custom boundary explicit while allowing a safe expression
        # to participate in normal downstream code generation.
        return f"(lambda df: ({expression}))({parent})"
    if node.type in {"utility.group", "utility.note", "utility.component_output"}:
        parent = parents.get("in") or next(iter(parents.values()), "spark.range(0)")
        return parent
    if node.type == "transform.join":
        left = parents["left"]
        right = parents["right"]
        how = cfg.get("how", "inner")
        if how == "cross":
            return f"{left}.crossJoin({right})"
        condition = cfg.get("condition", "")
        # SQL expressions using left/right aliases are compiled safely through expr.
        return f'{left}.alias("left").join({right}.alias("right"), F.expr({_py(condition)}), {_py(how)})'

    parent = parents.get("in") or next(iter(parents.values()))
    if node.type == "transform.filter":
        return f"{parent}.filter(F.expr({_py(cfg.get('expression', ''))}))"
    if node.type == "transform.select":
        columns = cfg.get("columns") or ["*"]
        args = ", ".join(f"F.expr({_py(c)})" if c != "*" else '"*"' for c in columns)
        return f"{parent}.select({args})"
    if node.type == "transform.derive":
        return f"{parent}.withColumn({_py(cfg.get('name', 'derived'))}, F.expr({_py(cfg.get('expression', ''))}))"
    if node.type == "transform.sql_project":
        return f"{parent}.selectExpr({_py(cfg.get('query', ''))})"
    if node.type == "transform.pyspark_block":
        code = str(cfg.get("code", "")).strip()
        if not code:
            raise ValueError("transform.pyspark_block requires code")
        return code.replace("$input", parent)
    if node.type == "transform.drop":
        columns = cfg.get("columns") or []
        return f"{parent}.drop({', '.join(_py(c) for c in columns)})"
    if node.type == "transform.rename":
        expr: str = parent
        for old, new in sorted((cfg.get("mapping") or {}).items()):
            expr += f".withColumnRenamed({_py(str(old))}, {_py(str(new))})"
        return expr
    if node.type == "transform.distinct":
        return f"{parent}.distinct()"
    if node.type == "transform.reorder":
        columns = cfg.get("columns") or []
        return f"{parent}.select({', '.join(_py(str(c)) for c in columns)})"
    if node.type == "transform.replace":
        column = str(cfg.get("column", ""))
        expression = f"F.col({_py(column)})"
        for old, new in sorted((cfg.get("mapping") or {}).items(), key=lambda item: str(item[0])):
            expression = f"F.when({expression} == {_py(old)}, {_py(new)}).otherwise({expression})"
        return f"{parent}.withColumn({_py(column)}, {expression})"
    if node.type == "transform.intersect":
        return f"{parents['left']}.intersect({parents['right']})"
    if node.type == "transform.except":
        return f"{parents['left']}.exceptAll({parents['right']})"
    if node.type == "transform.flatten_struct":
        column = str(cfg.get("column", ""))
        return f"{parent}.select('*', F.col({_py(column)} + '.*')).drop({_py(column)})"
    if node.type == "transform.build_struct":
        fields = cfg.get("fields") or {}
        expressions = ", ".join(
            f"F.expr({_py(str(expression))}).alias({_py(str(name))})"
            for name, expression in sorted(fields.items())
        )
        return f"{parent}.withColumn({_py(cfg.get('target', 'struct'))}, F.struct({expressions}))"
    if node.type == "transform.build_map":
        map_expressions: list[str] = []
        for key, value in zip(cfg.get("keys") or [], cfg.get("values") or [], strict=False):
            map_expressions.extend([f"F.expr({_py(str(key))})", f"F.expr({_py(str(value))})"])
        return f"{parent}.withColumn({_py(cfg.get('target', 'map'))}, F.create_map({', '.join(map_expressions)}))"
    if node.type == "transform.build_array":
        expressions = ", ".join(
            f"F.expr({_py(str(value))})" for value in cfg.get("expressions") or []
        )
        return f"{parent}.withColumn({_py(cfg.get('target', 'array'))}, F.array({expressions}))"
    if node.type == "transform.cast":
        return f"{parent}.withColumn({_py(cfg.get('column', ''))}, F.col({_py(cfg.get('column', ''))}).cast({_py(cfg.get('dataType', 'string'))}))"
    if node.type == "transform.fill_nulls":
        return f"{parent}.fillna({_py(cfg.get('values') or {})})"
    if node.type == "transform.drop_nulls":
        subset = cfg.get("subset") or []
        return f"{parent}.dropna(how={_py(cfg.get('how', 'any'))}, subset={_py(subset)})"
    if node.type == "transform.drop_duplicates":
        columns = cfg.get("columns") or []
        return (
            f"{parent}.dropDuplicates({_py(columns)})" if columns else f"{parent}.dropDuplicates()"
        )
    if node.type == "transform.deduplicate_event_time":
        columns = [str(value) for value in cfg.get("columns") or []]
        event_time = str(cfg.get("eventTime", "event_time"))
        if not columns:
            raise ValueError("deduplicate_event_time requires key columns")
        return f"{parent}.withWatermark({event_time!r}, {str(cfg.get('watermark', '10 minutes'))!r}).dropDuplicates([{', '.join(repr(value) for value in columns)}])"
    if node.type == "transform.union_by_name":
        return f"{parents['left']}.unionByName({parents['right']}, allowMissingColumns={bool(cfg.get('allowMissingColumns', False))})"
    if node.type == "transform.sort":
        exprs = ", ".join(f"F.expr({_py(e)})" for e in (cfg.get("expressions") or []))
        return f"{parent}.sort({exprs})"
    if node.type == "transform.limit":
        return f"{parent}.limit({int(cfg.get('count', 100))})"
    if node.type == "transform.explode":
        return f"{parent}.withColumn({_py(cfg.get('target', 'item'))}, F.explode(F.col({_py(cfg.get('column', ''))})))"
    if node.type == "transform.posexplode":
        position = str(cfg.get("position", "pos"))
        target = str(cfg.get("target", "item"))
        return (
            f"{parent}.select('*', F.posexplode(F.col({_py(cfg.get('column', ''))})))"
            f".withColumnRenamed('pos', {_py(position)}).withColumnRenamed('col', {_py(target)})"
        )
    if node.type == "transform.repartition":
        cols = cfg.get("columns") or []
        args = ", ".join(
            [str(int(cfg.get("partitions", 200)))] + [f"F.col({_py(c)})" for c in cols]
        )
        return f"{parent}.repartition({args})"
    if node.type == "transform.coalesce":
        return f"{parent}.coalesce({int(cfg.get('partitions', 1))})"
    if node.type == "transform.watermark":
        return f"{parent}.withWatermark({_py(cfg.get('column', ''))}, {_py(cfg.get('delay', ''))})"
    if node.type == "transform.json_parse":
        return f"{parent}.withColumn({_py(cfg.get('target', 'parsed'))}, F.from_json(F.col({_py(cfg.get('column', ''))}), {_py(cfg.get('schema', ''))}))"
    if node.type == "transform.window":
        partitions = ", ".join(f"F.col({_py(value)})" for value in cfg.get("partitionBy") or [])
        ordering = ", ".join(f"F.col({_py(value)})" for value in cfg.get("orderBy") or [])
        window = "Window.partitionBy(" + partitions + ")" if partitions else "Window.partitionBy()"
        if ordering:
            window += ".orderBy(" + ordering + ")"
        return f"{parent}.withColumn({_py(cfg.get('target', 'window_value'))}, F.expr({_py(cfg.get('expression', ''))}).over({window}))"
    if node.type.startswith("quality."):
        # Quality metadata is consumed by the runtime/debugger. Keep dataset
        # definitions planning-safe: never add count(), writes, or actions here.
        return parent
    if node.type == "transform.aggregate":
        groups = cfg.get("groupBy") or []
        aggs = cfg.get("aggregations") or []
        group_expr = ", ".join(f"F.expr({_py(g)})" for g in groups)
        agg_expr = ", ".join(
            f"F.expr({_py(a.get('expression', 'count(*)'))}).alias({_py(a.get('alias', 'value'))})"
            for a in aggs
        )
        if groups:
            return f"{parent}.groupBy({group_expr}).agg({agg_expr})"
        return f"{parent}.agg({agg_expr})"
    raise ValueError(f"unsupported transform {node.type}")


def _dataset_reference_expr(node: Any) -> str:
    name = str(node.config.get("name", ""))
    if node.type == "dataset.streaming_table":
        return f"spark.readStream.table({_py(name)})"
    return f"spark.table({_py(name)})"


def _definition_scope(index: GraphIndex, definition_id: str) -> set[str]:
    """Ancestors needed inside one SDP definition, stopping at declared dataset boundaries."""
    seen: set[str] = set()
    stack = [edge.from_.node for edge in index.incoming.get(definition_id, [])]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = index.nodes[node_id]
        if node.type.startswith("dataset."):
            continue
        for edge in index.incoming.get(node_id, []):
            stack.append(edge.from_.node)
    return seen


def generate_python_project(
    document: PipelineDocument, project_root: Path | None = None, *, runtime_hooks: bool = False
) -> GenerationResult:
    lowered = lower_pipeline(document)
    ir_document = lowered.pipeline.graph_view()
    problems = list(lowered.problems) + _semantic_problems(ir_document)
    if has_errors(problems):
        return GenerationResult(files=[], source_map=[], problems=problems)

    document = ir_document
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
    topological = index.topological_order()
    definitions = [
        index.nodes[node_id] for node_id in topological if _is_definition(index.nodes[node_id])
    ]
    lines: list[str] = [
        "# Generated by SDP Studio. The visual model is the source of truth; do not hand edit this file.",
    ]
    if runtime_hooks or any(_has_secret_ref(node.config) for node in document.nodes):
        lines.append("import os")
        lines.append("")
    if runtime_hooks:
        lines.extend(
            [
                "import contextlib",
                "import io",
                "import json",
                "",
                "def _sdpstudio_capture_plan(node_id, dataframe):",
                '    destination = os.environ.get("SDPSTUDIO_PLAN_ARTIFACT_DIR")',
                "    if not destination:",
                "        return",
                "    buffer = io.StringIO()",
                "    with contextlib.redirect_stdout(buffer):",
                '        dataframe.explain(mode="extended")',
                "    os.makedirs(destination, exist_ok=True)",
                '    with open(os.path.join(destination, f"{node_id}.json"), "w", encoding="utf-8") as handle:',
                '        json.dump({"node_id": node_id, "raw": buffer.getvalue()}, handle, sort_keys=True)',
                '        handle.write("\\n")',
                "",
                "def _sdpstudio_quality_check(node_id, dataframe, check):",
                '    limit = max(1, min(int(os.environ.get("SDPSTUDIO_QUALITY_SAMPLE_ROWS", "200")), 2000))',
                "    rows = [json.loads(value) for value in dataframe.limit(limit).toJSON().collect()]",
                '    result = evaluate_quality(check["type"], check["config"], rows)',
                '    destination = os.environ.get("SDPSTUDIO_QUALITY_ARTIFACT_DIR")',
                "    if destination:",
                "        os.makedirs(destination, exist_ok=True)",
                '        with open(os.path.join(destination, f"{node_id}.json"), "w", encoding="utf-8") as handle:',
                "            json.dump(result, handle, sort_keys=True)",
                '            handle.write("\\n")',
                '        quarantine = result.get("quarantine", [])',
                "        if quarantine:",
                '            with open(os.path.join(destination, f"{node_id}.quarantine.json"), "w", encoding="utf-8") as handle:',
                "                json.dump(quarantine, handle, sort_keys=True)",
                '                handle.write("\\n")',
                '    if result.get("status") == "failed" and os.environ.get("SDPSTUDIO_QUALITY_FAIL_ON_ERROR", "false").lower() == "true":',
                '        raise RuntimeError(f"Quality check failed: {node_id}")',
                "    return dataframe",
                "",
            ]
        )
    lines.extend(
        [
            "from pyspark import pipelines as dp",
            "from pyspark.sql import DataFrame",
            "from pyspark.sql import functions as F",
        ]
    )
    if runtime_hooks:
        lines.append("from sdpstudio_core.quality import evaluate_quality")
    if any(node.type == "transform.window" for node in document.nodes):
        lines.append("from pyspark.sql.window import Window")
    lines.extend(
        [
            "",
            "sdpstudio_quality_checks = []",
            "",
            "",
        ]
    )
    source_map: list[SourceRange] = []

    for output in definitions:
        name = str(output.config.get("name", "dataset"))
        function = _identifier(name)
        output_start_line = len(lines) + 1
        if output.type == "sink.external":
            options_expr = _options_dict_py(output.config.get("options") or {})
            lines.append(
                f"dp.create_sink(name={_py(name)}, format={_py(output.config.get('format', ''))}, options={options_expr})"
            )
            flow_name = f"flow_{function}"
            lines.append(f"@dp.append_flow(target={_py(name)}, name={_py(flow_name)})")
            lines.append(f"def {flow_name}() -> DataFrame:")
        else:
            decorator = {
                "dataset.materialized_view": f"@dp.materialized_view(name={_py(name)})",
                "dataset.streaming_table": f"@dp.table(name={_py(name)})",
                "dataset.temporary_view": f"@dp.temporary_view(name={_py(name)})",
                "dataset.auto_cdc_scd1": f"@dp.create_auto_cdc_flow(target={_py(name)}, keys={_py(output.config.get('keys') or [])}, sequence_by=F.col({_py(output.config.get('sequence_by', ''))}))",
            }[output.type]
            lines.append(decorator)
            lines.append(f"def {function}() -> DataFrame:")

        needed = _definition_scope(index, output.id)
        order = [nid for nid in topological if nid in needed]
        if not order:
            lines.append(
                '    raise RuntimeError("SDP Studio generated an empty dataset definition")'
            )
        for node_id in order:
            node = index.nodes[node_id]
            var = _var(node.id)
            start_line = len(lines) + 1
            if project_root is not None or runtime_hooks:
                lines.append(f"    # sdpstudio:region node={node.id} ownership=visual")
            if node.type.startswith("source.") or node.type == "utility.component_input":
                expr = _source_expr(node)
            elif node.type.startswith("dataset."):
                expr = _dataset_reference_expr(node)
            else:
                parents: dict[str, str] = {}
                for edge in sorted(
                    index.incoming.get(node.id, []), key=lambda e: (e.to.port, e.id)
                ):
                    parent_port = (
                        edge.from_.port
                        if index.nodes[edge.from_.node].type == "quality.quarantine_split"
                        else None
                    )
                    parents[edge.to.port] = _var(edge.from_.node, parent_port)
                try:
                    expr = _transform_expr(node, parents)
                except ValueError as exc:
                    problems.append(
                        Problem(
                            code="SDPS-CODEGEN-002",
                            severity="error",
                            message=str(exc),
                            node_id=node.id,
                            remediation="Preserve the custom source block or replace it with a supported operator before generating.",
                        )
                    )
                    continue
                if node.type == "quality.quarantine_split":
                    source_expr = parents.get("in") or next(iter(parents.values()), "")
                    column = _py(str(node.config.get("column", "")))
                    lines.append(
                        f"    {var} = {source_expr}.filter(F.col({column}).isNotNull() & (F.col({column}) != ''))"
                    )
                    lines.append(
                        f"    {_var(node.id, 'quarantine')} = {source_expr}.filter(F.col({column}).isNull() | (F.col({column}) == ''))"
                    )
                elif node.type.startswith("quality."):
                    lines.append(
                        f"    sdpstudio_quality_checks.append({_py({'node_id': node.id, 'type': node.type, 'config': node.config})})"
                    )
            if node.type == "quality.quarantine_split":
                pass
            elif runtime_hooks and node.type.startswith("quality."):
                lines.append(
                    f"    {var} = _sdpstudio_quality_check({_py(node.id)}, {expr}, {_py({'type': node.type, 'config': node.config})})"
                )
            else:
                lines.append(f"    {var} = {expr}")
            if runtime_hooks and not node.type.startswith("source."):
                lines.append(f"    _sdpstudio_capture_plan({_py(node.id)}, {var})")
            if project_root is not None or runtime_hooks:
                lines.append("    # sdpstudio:endregion")
            source_map.append(
                SourceRange(
                    node_id=node.id,
                    file="transformations/generated.py",
                    start_line=start_line,
                    end_line=start_line,
                )
            )

        incoming = index.incoming.get(output.id, [])
        upstream_edge = incoming[0]
        upstream_node = index.nodes[upstream_edge.from_.node]
        upstream = _var(
            upstream_edge.from_.node,
            upstream_edge.from_.port if upstream_node.type == "quality.quarantine_split" else None,
        )
        return_line = len(lines) + 1
        lines.append(f"    return {upstream}")
        source_map.append(
            SourceRange(
                node_id=output.id,
                file="transformations/generated.py",
                start_line=output_start_line,
                end_line=return_line,
            )
        )
        lines.extend(["", ""])

    if has_errors(problems):
        return GenerationResult(files=[], source_map=source_map, problems=problems)
    content = "\n".join(lines).rstrip() + "\n"
    generated_hash = _sha256(content)
    source_map = [
        mapping.model_copy(
            update={
                "object_id": f"node:{mapping.node_id}:definition",
                "start_column": 1,
                "end_column": len(content.splitlines()[mapping.start_line - 1]) + 1,
                "content_hash": generated_hash,
            }
        )
        for mapping in source_map
    ]
    generated = [
        GeneratedFile(path="transformations/generated.py", content=content, sha256=generated_hash)
    ]

    if project_root is not None:
        # Permit deployment environments (including WSL) to substitute their
        # own absolute URI while retaining a native local default.
        storage = os.environ.get(
            "SDPSTUDIO_STORAGE_URI",
            (project_root / ".sdpstudio" / "runtime" / "storage").resolve().as_uri(),
        )
        event_logs = os.environ.get(
            "SDPSTUDIO_EVENT_LOG_URI",
            (project_root / ".sdpstudio" / "runtime" / "event-logs").resolve().as_uri(),
        )
        spec = (
            f"name: {document.name}\n"
            "libraries:\n"
            "  - glob:\n"
            "      include: transformations/**\n"
            f"storage: {storage}\n"
            "configuration:\n"
            '  spark.eventLog.enabled: "true"\n'
            f'  spark.eventLog.dir: "{event_logs}"\n'
        )
        generated.append(
            GeneratedFile(path="spark-pipeline.yaml", content=spec, sha256=_sha256(spec))
        )

    return GenerationResult(files=generated, source_map=source_map, problems=problems)
