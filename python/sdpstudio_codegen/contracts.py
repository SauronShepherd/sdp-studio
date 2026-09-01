from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from sdpstudio_core.ir import IRPipeline
from sdpstudio_core.models import GenerationResult


@dataclass(frozen=True)
class CodegenContext:
    """Provider-neutral options supplied to a code-generation backend."""

    project_root: Path | None = None
    runtime_hooks: bool = False


# Public name used by the compiler contract; the existing model already has
# the required files, source mappings, diagnostics, and content hashes.
GeneratedProject = GenerationResult


@dataclass(frozen=True)
class SupportReport:
    supported: bool
    reasons: tuple[str, ...] = ()


class CodegenBackend(Protocol):
    target: Literal["python", "sql"]

    def supports(self, ir: IRPipeline) -> SupportReport: ...

    def generate(self, ir: IRPipeline, ctx: CodegenContext | None = None) -> GeneratedProject: ...


class PythonCodegenBackend:
    target: Literal["python"] = "python"

    def supports(self, ir: IRPipeline) -> SupportReport:
        unsupported = tuple(
            sorted({node.operator for node in ir.nodes if node.operator == "utility.custom_code"})
        )
        return SupportReport(not unsupported, unsupported)

    def generate(self, ir: IRPipeline, ctx: CodegenContext | None = None) -> GeneratedProject:
        from .python_backend import generate_python_project

        ctx = ctx or CodegenContext()
        return generate_python_project(
            ir.graph_view(), ctx.project_root, runtime_hooks=ctx.runtime_hooks
        )


class SqlCodegenBackend:
    target: Literal["sql"] = "sql"

    def supports(self, ir: IRPipeline) -> SupportReport:
        unsupported_operators = {
            "utility.custom_code",
            "source.custom_pyspark",
            "transform.pyspark_block",
            "transform.drop",
            "transform.flatten_struct",
            "transform.intersect",
            "transform.except",
        }
        unsupported = tuple(
            sorted({node.operator for node in ir.nodes if node.operator in unsupported_operators})
        )
        return SupportReport(not unsupported, unsupported)

    def generate(self, ir: IRPipeline, ctx: CodegenContext | None = None) -> GeneratedProject:
        from .sql_backend import generate_sql_project

        return generate_sql_project(ir.graph_view())


def choose_target(preference: str, *, sql_supported: bool = True) -> str:
    """Resolve an explicit user preference without silently selecting SQL when unavailable."""
    if preference not in {"python", "sql", "auto"}:
        raise ValueError("target must be python, sql, or auto")
    if preference == "sql" and not sql_supported:
        raise ValueError("SQL target is unavailable for this pipeline")
    return (
        "python"
        if preference == "auto" and not sql_supported
        else ("python" if preference == "auto" else preference)
    )
