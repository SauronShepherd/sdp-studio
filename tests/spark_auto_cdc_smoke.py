"""Validate the generated Auto CDC SCD1 shape against an installed Spark 4.2 runtime.

This gate is intentionally environment-backed: the default test suite remains
credential-free, while Spark qualification fails closed unless the reference
runtime is installed and exposes the pipelines API.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from sdpstudio_codegen.python_backend import generate_python_project
from sdpstudio_core.models import Edge, Node, PipelineDocument


def main() -> int:
    try:
        import pyspark
        from pyspark import pipelines  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Spark 4.2 with pyspark.pipelines is required for Auto CDC qualification"
        ) from exc
    if not str(pyspark.__version__).startswith("4.2"):
        raise SystemExit(f"Spark 4.2 is required, found {pyspark.__version__}")

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
    call = calls[0]
    keywords = {item.arg for item in call.keywords}
    if not {"target", "keys", "sequence_by"}.issubset(keywords):
        raise SystemExit("generated Auto CDC call is missing target, keys, or sequence_by")
    print(f"AUTO_CDC_SPARK_42_OK version={pyspark.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
