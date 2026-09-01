"""Small deterministic performance smoke benchmark used by CI."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from sdpstudio_codegen import generate_python_project
from sdpstudio_core.graph import validate_graph
from sdpstudio_core.models import Edge, Node, PipelineDocument, PortRef


def sample_document(size: int = 25) -> PipelineDocument:
    nodes = [
        Node(
            id=f"node-{index}",
            type="source.table" if index == 0 else "transform.filter",
            config={"table": "demo.orders", "streaming": False}
            if index == 0
            else {"expression": "id >= 0"},
        )
        for index in range(size)
    ]
    output = Node(
        id="output", type="dataset.materialized_view", config={"name": "benchmark_output"}
    )
    nodes.append(output)
    edges = [
        Edge(
            **{
                "from": PortRef(node=nodes[index].id),
                "to": PortRef(node=nodes[index + 1].id, port="in"),
            }
        )
        for index in range(size - 1)
    ]
    edges.append(
        Edge(**{"from": PortRef(node=nodes[size - 1].id), "to": PortRef(node=output.id, port="in")})
    )
    return PipelineDocument(name="benchmark", nodes=nodes, edges=edges)


def run(iterations: int = 3, size: int = 25) -> dict[str, float | int]:
    if size < 1:
        raise ValueError("Benchmark size must be positive")
    document = sample_document(size)
    started = time.perf_counter()
    problems = 0
    for _ in range(iterations):
        problems += len(validate_graph(document))
        generate_python_project(document)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "iterations": iterations,
        "nodes": len(document.nodes),
        "elapsed_ms": round(elapsed_ms, 3),
        "problems": problems,
    }


def run_scale(iterations: int = 1, sizes: tuple[int, ...] = (25, 500, 1000)) -> dict[str, object]:
    """Run the required small and scale regression sizes deterministically."""
    return {"benchmarks": [run(iterations=iterations, size=size) for size in sizes]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-ms", type=float, default=5000)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--sizes", nargs="+", type=int, default=[25])
    args = parser.parse_args()
    result = (
        run_scale(iterations=max(1, args.iterations), sizes=tuple(args.sizes))
        if len(args.sizes) > 1
        else run(iterations=max(1, args.iterations), size=args.sizes[0])
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if "benchmarks" in result:
        return 0 if all(item["elapsed_ms"] <= args.max_ms for item in result["benchmarks"]) else 1
    return 0 if result["elapsed_ms"] <= args.max_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
