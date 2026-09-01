from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sdpstudio_core.graph import GraphIndex
from sdpstudio_core.ir import lower_pipeline
from sdpstudio_core.models import GenerationResult, PipelineDocument, Problem

from .python_backend import generate_python_project
from .sql_backend import generate_sql_project


@dataclass(frozen=True)
class DatasetLanguagePlan:
    """Deterministic language assignment and explanation for one output dataset."""

    dataset_id: str
    language: Literal["python", "sql"]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class MixedLanguagePlan:
    assignments: tuple[DatasetLanguagePlan, ...]
    problems: tuple[Problem, ...] = ()


_SQL_UNSUPPORTED = {
    "utility.custom_code": "custom code requires the Python backend",
    "transform.drop": "drop requires explicit SQL projection columns",
    "transform.flatten_struct": "flatten_struct requires schema-aware Python lowering",
    "transform.intersect": "intersect requires binary SQL lowering",
    "transform.except": "except requires binary SQL lowering",
}


def plan_pipeline(
    document: PipelineDocument, preference: Literal["auto", "python", "sql"] = "auto"
) -> MixedLanguagePlan:
    """Assign each output to a backend with deterministic reasons.

    Explicit preferences preserve the existing all-Python/all-SQL behavior.
    ``auto`` chooses SQL for independently SQL-compatible output subgraphs and
    Python only where a supported SQL lowering is unavailable.
    """
    if preference not in {"auto", "python", "sql"}:
        raise ValueError("preference must be auto, python, or sql")
    lowered = lower_pipeline(document)
    index = GraphIndex(lowered.pipeline.graph_view())
    nodes = index.nodes
    assignments: list[DatasetLanguagePlan] = []
    problems: list[Problem] = list(lowered.problems)
    for node_id in index.topological_order():
        node = nodes[node_id]
        if not node.type.startswith("dataset."):
            continue
        unsupported: list[str] = []
        seen: set[str] = set()
        stack = [edge.from_.node for edge in index.incoming.get(node_id, [])]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            current_node = nodes[current]
            if current_node.type in _SQL_UNSUPPORTED:
                unsupported.append(_SQL_UNSUPPORTED[current_node.type])
            stack.extend(edge.from_.node for edge in index.incoming.get(current, []))
        reasons: tuple[str, ...] = tuple(sorted(set(unsupported)))
        if preference == "python":
            language: Literal["python", "sql"] = "python"
            explanation: tuple[str, ...] = ("explicit Python target",)
        elif preference == "sql":
            language = "sql"
            explanation = reasons or ("explicit SQL target",)
            if reasons:
                problems.append(
                    Problem(
                        code="SDPS-CODEGEN-001",
                        severity="error",
                        message="Explicit SQL target is unsupported for this output subgraph.",
                        node_id=node_id,
                        details={"reasons": list(reasons)},
                        remediation="Choose Python or use auto backend selection.",
                    )
                )
        elif reasons:
            language = "python"
            explanation = reasons
        else:
            language = "sql"
            explanation = ("output subgraph is SQL-compatible",)
        assignments.append(DatasetLanguagePlan(node_id, language, explanation))
    return MixedLanguagePlan(tuple(assignments), tuple(problems))


def generate_project(
    document: PipelineDocument, target: Literal["python", "sql"] = "python", project_root=None
) -> GenerationResult:
    if target == "python":
        return generate_python_project(document, project_root)
    if target == "sql":
        return generate_sql_project(document)
    raise ValueError(f"unsupported code-generation target: {target}")
