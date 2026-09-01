"""Qualify Auto CDC against the actual installed Spark 4.2 Python API.

The OSS Spark capability is deliberately discovered instead of inferred from
version text.  Some Spark 4.2 distributions expose Auto CDC internals/error
classes without publishing ``pyspark.pipelines.create_auto_cdc_flow``.  In
that case SDP Studio must report the capability as unavailable rather than
claiming support because generated source happens to parse.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from sdpstudio_codegen.python_backend import generate_python_project
from sdpstudio_core.models import Edge, Node, PipelineDocument
from sdpstudio_runners.local import probe_local


def main() -> int:
    try:
        import pyspark
        from pyspark import pipelines
    except ImportError as exc:
        raise SystemExit(
            "Spark 4.2 with pyspark.pipelines is required for Auto CDC qualification"
        ) from exc
    if not str(pyspark.__version__).startswith("4.2"):
        raise SystemExit(f"Spark 4.2 is required, found {pyspark.__version__}")

    api = getattr(pipelines, "create_auto_cdc_flow", None)
    capability = probe_local().auto_cdc_scd1
    if api is None:
        if capability:
            raise SystemExit(
                "Runtime probe advertises auto_cdc_scd1 but pyspark.pipelines.create_auto_cdc_flow is absent"
            )
        print(f"AUTO_CDC_SPARK_42_UNAVAILABLE version={pyspark.__version__}")
        return 0

    if not callable(api):
        raise SystemExit("pyspark.pipelines.create_auto_cdc_flow exists but is not callable")

    document = PipelineDocument(
        name="auto-cdc-smoke",
        nodes=[
            Node(
                id="source",
                type="source.table",
                config={"table": "raw.customers", "streaming": True},
            ),
            Node(
                id="customers",
                type="dataset.auto_cdc_scd1",
                config={"name": "customers", "keys": ["id"], "sequence_by": "updated_at"},
            ),
        ],
        edges=[
            Edge.model_validate(
                {"from": {"node": "source"}, "to": {"node": "customers", "port": "in"}}
            )
        ],
    )
    result = generate_python_project(document)
    if result.problems:
        raise SystemExit("; ".join(problem.message for problem in result.problems))
    source = next(
        item.content for item in result.files if item.path == "transformations/generated.py"
    )
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_auto_cdc_flow"
    ]
    if len(calls) != 1:
        raise SystemExit(
            "generated Auto CDC source did not contain exactly one create_auto_cdc_flow call"
        )

    signature = inspect.signature(api)
    accepted = set(signature.parameters)
    keywords = {item.arg for item in calls[0].keywords if item.arg is not None}
    unsupported = keywords - accepted
    if unsupported:
        raise SystemExit(
            "generated Auto CDC call uses unsupported arguments: " + ", ".join(sorted(unsupported))
        )
    if not {"target", "keys", "sequence_by"}.issubset(keywords):
        raise SystemExit("generated Auto CDC call is missing target, keys, or sequence_by")
    if not capability:
        raise SystemExit(
            "Spark exposes create_auto_cdc_flow but RuntimeCapabilities.auto_cdc_scd1 is false"
        )

    print(f"AUTO_CDC_SPARK_42_OK version={pyspark.__version__} signature={signature}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
