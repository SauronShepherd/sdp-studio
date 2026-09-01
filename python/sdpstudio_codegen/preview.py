from __future__ import annotations

from sdpstudio_core.graph import GraphIndex, has_errors, validate_graph
from sdpstudio_core.models import PipelineDocument, Problem

from .python_backend import (
    _has_secret_ref,
    _source_expr,
    _transform_expr,
    _var,
)


def _preview_scope(index: GraphIndex, node_id: str) -> tuple[set[str], str]:
    target = index.nodes[node_id]
    if target.type.startswith("dataset.") or target.type.startswith("sink."):
        incoming = index.incoming.get(node_id, [])
        if not incoming:
            return set(), ""
        root = incoming[0].from_.node
    else:
        root = node_id

    seen: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        node = index.nodes[current]
        # A declared dataset is a durable pipeline boundary. Preview its current snapshot
        # instead of rebuilding everything that produced it.
        if node.type.startswith("dataset."):
            continue
        for edge in index.incoming.get(current, []):
            stack.append(edge.from_.node)
    return seen, root


def generate_preview_script(
    document: PipelineDocument,
    node_id: str,
    *,
    limit: int = 50,
    remote_from_env: bool = False,
    include_plan: bool = False,
    include_profile: bool = False,
    include_trace: bool = False,
    confirm_sink_test: bool = False,
    sampling_fraction: float = 1.0,
    seed: int = 0,
    profile_max_rows: int = 200,
    profile_max_columns: int = 100,
    profile_top_values: int = 5,
) -> tuple[str | None, list[Problem]]:
    problems = validate_graph(document)
    index = GraphIndex(document)
    if node_id not in index.nodes:
        problems.append(
            Problem(
                code="SDPS-PREVIEW-001",
                severity="error",
                message="Preview node does not exist",
                node_id=node_id,
            )
        )
        return None, problems
    if limit < 1 or limit > 200:
        problems.append(
            Problem(
                code="SDPS-PREVIEW-002",
                severity="error",
                message="Preview limit must be between 1 and 200",
                node_id=node_id,
            )
        )
        return None, problems
    if sampling_fraction <= 0 or sampling_fraction > 1 or seed < 0:
        problems.append(
            Problem(
                code="SDPS-PREVIEW-019",
                severity="error",
                message="Preview sampling fraction must be > 0 and <= 1; seed must be non-negative",
                node_id=node_id,
            )
        )
        return None, problems
    if index.nodes[node_id].type.startswith("sink.") and not confirm_sink_test:
        problems.append(
            Problem(
                code="SDPS-PREVIEW-020",
                severity="error",
                message="Previewing a sink requires explicit confirmation because it may have side effects",
                node_id=node_id,
                remediation="Confirm the sink test explicitly or preview its upstream dataset instead.",
            )
        )
        return None, problems
    if has_errors(problems):
        return None, problems

    scope, root = _preview_scope(index, node_id)
    if not root:
        problems.append(
            Problem(
                code="SDPS-PREVIEW-003",
                severity="error",
                message="Node has no upstream DataFrame to preview",
                node_id=node_id,
            )
        )
        return None, problems

    for scoped_id in scope:
        node = index.nodes[scoped_id]
        if node.type == "source.kafka" or (
            node.type.startswith("source.") and bool(node.config.get("streaming"))
        ):
            problems.append(
                Problem(
                    code="SDPS-PREVIEW-004",
                    severity="error",
                    message="Direct preview of an unmaterialized streaming source is not supported",
                    node_id=scoped_id,
                    remediation="Run/materialize the streaming dataset first, then preview downstream from the declared streaming table boundary.",
                )
            )
    if has_errors(problems):
        return None, problems

    if (
        profile_max_rows < 1
        or profile_max_rows > 100_000
        or profile_max_columns < 1
        or profile_max_columns > 1_000
        or profile_top_values < 0
        or profile_top_values > 100
    ):
        problems.append(
            Problem(
                code="SDPS-PREVIEW-018",
                severity="error",
                message="Profile limits are outside the supported safety bounds",
                node_id=node_id,
            )
        )
        return None, problems
    lines = [
        "# Ephemeral SDP Studio data-preview program. This is not pipeline source code.",
        "import json",
        "import contextlib",
        "import io",
        "import os",
        "import time",
        "from pyspark.sql import SparkSession",
        "from pyspark.sql import functions as F",
        *(["from sdpstudio_core.debug import profile_rows"] if include_profile else []),
        "",
        'builder = SparkSession.builder.appName("SDP Studio Data Preview")',
    ]
    if remote_from_env:
        lines.append('builder = builder.remote(os.environ["SDPSTUDIO_PREVIEW_REMOTE"])')
    lines.append("spark = builder.getOrCreate()")
    if include_trace:
        lines.extend(
            [
                "def __svp_ensure_trace_id(df):",
                "    return df if '__sdpstudio_trace_id' in df.columns else df.withColumn('__sdpstudio_trace_id', F.monotonically_increasing_id())",
            ]
        )
    lines.append("try:")

    order = [nid for nid in index.topological_order() if nid in scope]
    for current in order:
        node = index.nodes[current]
        var = _var(current)
        if node.type.startswith("source."):
            expr = _source_expr(node)
        elif node.type.startswith("dataset."):
            # Preview an existing materialized snapshot even when the declared dataset is streaming.
            expr = f"spark.table({str(node.config.get('name', ''))!r})"
        else:
            parents: dict[str, str] = {}
            for edge in sorted(index.incoming.get(current, []), key=lambda e: (e.to.port, e.id)):
                if edge.from_.node in scope:
                    parents[edge.to.port] = _var(edge.from_.node)
            expr = _transform_expr(node, parents)
        lines.append(f"    {var} = {expr}")
        if include_trace:
            lines.append(f"    {var} = __svp_ensure_trace_id({var})")

    target_var = _var(root)
    lines.extend(
        [
            f"    __svp_df = {target_var}",
            "    __svp_started = time.perf_counter()",
            *(
                [
                    "    __svp_trace_df = __svp_ensure_trace_id(__svp_df)",
                ]
                if include_trace
                else []
            ),
            f"    __svp_sampled_df = __svp_df.sample(withReplacement=False, fraction={float(sampling_fraction)!r}, seed={int(seed)})",
            f"    __svp_rows = [json.loads(x) for x in __svp_sampled_df.limit({int(limit)}).toJSON().collect()]",
            "    __svp_payload = {",
            '        "schema": json.loads(__svp_df.schema.json()),',
            '        "rows": __svp_rows,',
            '        "metrics": {"row_count": len(__svp_rows)},',
            f'        "limit": {int(limit)},',
            f'        "node_id": {node_id!r},',
            *(
                [
                    f"        'trace_rows': [json.loads(x) for x in __svp_trace_df.limit({int(limit)}).toJSON().collect()],",
                    "        'trace_instrumentation': 'spark_monotonically_increasing_id',",
                    "        'trace_nodes': {",
                    *[
                        f"            {scoped_id!r}: [json.loads(x) for x in {_var(scoped_id)}.limit({int(limit)}).toJSON().collect()],"
                        for scoped_id in order
                    ],
                    "        },",
                ]
                if include_trace
                else []
            ),
            "    }",
            *(
                [
                    "    __svp_plan_buffer = io.StringIO()",
                    "    with contextlib.redirect_stdout(__svp_plan_buffer):",
                    '        __svp_df.explain(mode="extended")',
                    '    __svp_payload["plan"] = __svp_plan_buffer.getvalue()',
                ]
                if include_plan
                else []
            ),
            *(
                [
                    f"    __svp_profile_rows = [json.loads(x) for x in __svp_df.limit({int(profile_max_rows)}).toJSON().collect()]",
                    f'    __svp_payload["profile"] = profile_rows(__svp_profile_rows, max_rows={int(profile_max_rows)}, max_columns={int(profile_max_columns)}, top_values={int(profile_top_values)})',
                ]
                if include_profile
                else []
            ),
            '    __svp_payload["metrics"]["elapsed_ms"] = round((time.perf_counter() - __svp_started) * 1000, 3)',
            '    __svp_payload["metrics"]["profile_bounded"] = True',
            '    print("__SDPSTUDIO_PREVIEW_BEGIN__")',
            '    print(json.dumps(__svp_payload, default=str, separators=(",", ":")))',
            '    print("__SDPSTUDIO_PREVIEW_END__")',
            "finally:",
            "    spark.stop()",
            "",
        ]
    )
    # os is intentionally always imported: remote configuration and secret references are
    # passed through environment variables and never embedded in the script.
    _ = any(_has_secret_ref(index.nodes[n].config) for n in scope)
    script = "\n".join(lines)
    try:
        compile(script, "<sdpstudio-preview>", "exec")
    except SyntaxError as exc:  # defensive compiler invariant
        return None, [
            Problem(
                code="SDPS-PREVIEW-900",
                severity="error",
                message=f"Internal preview compiler error: {exc}",
                node_id=node_id,
            )
        ]
    return script, problems
