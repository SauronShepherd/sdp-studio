from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Declaration:
    name: str
    kind: str
    file: str
    start_line: int
    end_line: int
    function: str | None = None
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class CustomCodeArtifact:
    file: str
    start_line: int
    end_line: int
    source: str
    reason: str
    source_sha256: str


@dataclass(frozen=True)
class ImportReport:
    declarations: tuple[Declaration, ...]
    unsupported: tuple[str, ...] = ()
    source_sha256: str = ""
    custom_code: tuple[CustomCodeArtifact, ...] = ()


def source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def source_changed(original_sha256: str, source: str) -> bool:
    return original_sha256 != source_hash(source)


def _literal_name(decorator: ast.Call) -> str | None:
    for keyword in decorator.keywords:
        if (
            keyword.arg in {"name", "target"}
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        ):
            return keyword.value.value
    if (
        decorator.args
        and isinstance(decorator.args[0], ast.Constant)
        and isinstance(decorator.args[0].value, str)
    ):
        return decorator.args[0].value
    return None


def discover_python(path: Path, source: str | None = None) -> ImportReport:
    """Discover SDP declarations without importing or executing user code."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    declarations: list[Declaration] = []
    unsupported: list[str] = []
    decorator_calls: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            if call is not None:
                decorator_calls.add(id(call))
            decorator_target = call.func if call else decorator
            if (
                not isinstance(decorator_target, ast.Attribute)
                or not isinstance(decorator_target.value, ast.Name)
                or decorator_target.value.id != "dp"
            ):
                continue
            kind_map = {
                "materialized_view": "dataset.materialized_view",
                "table": "dataset.streaming_table",
                "temporary_view": "dataset.temporary_view",
                "append_flow": "sink.external",
                "create_auto_cdc_flow": "dataset.auto_cdc_scd1",
            }
            kind = kind_map.get(decorator_target.attr)
            if not kind:
                unsupported.append(decorator_target.attr)
                continue
            name = _literal_name(call) if call else None
            dependencies: set[str] = set()
            for child in ast.walk(node):
                if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                    continue
                if child.func.attr != "table" or not child.args:
                    continue
                argument = child.args[0]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    dependencies.add(argument.value)
                elif _is_spark_table_call(child.func):
                    unsupported.append("dynamic_dependency")
            declarations.append(
                Declaration(
                    name or node.name,
                    kind,
                    str(path),
                    node.lineno,
                    getattr(node, "end_lineno", node.lineno),
                    node.name,
                    tuple(sorted(dependencies)),
                )
            )
    call_kinds = {
        "create_streaming_table": "dataset.streaming_table",
        "create_materialized_view": "dataset.materialized_view",
        "create_sink": "sink.external",
        "create_auto_cdc_flow": "dataset.auto_cdc_scd1",
    }
    for invocation in ast.walk(tree):
        if not isinstance(invocation, ast.Call) or id(invocation) in decorator_calls:
            continue
        call_target = invocation.func
        if (
            not isinstance(call_target, ast.Attribute)
            or not isinstance(call_target.value, ast.Name)
            or call_target.value.id != "dp"
        ):
            continue
        kind = call_kinds.get(call_target.attr)
        if not kind:
            continue
        name = _literal_name(invocation)
        if not name:
            for keyword in invocation.keywords:
                if (
                    keyword.arg in {"target", "table"}
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    name = keyword.value.value
                    break
        if not name:
            unsupported.append("dynamic_declaration_name")
            continue
        declarations.append(
            Declaration(
                name,
                kind,
                str(path),
                invocation.lineno,
                getattr(invocation, "end_lineno", invocation.lineno),
            )
        )
    digest = source_hash(text)
    custom_code: tuple[CustomCodeArtifact, ...] = ()
    if unsupported or not declarations:
        custom_code = (
            CustomCodeArtifact(
                str(path),
                1,
                max(1, text.count("\n") + 1),
                text,
                "Unsupported or code-owned Python was preserved verbatim",
                digest,
            ),
        )
    return ImportReport(tuple(declarations), tuple(sorted(set(unsupported))), digest, custom_code)


def _is_spark_read_table(function: ast.Attribute) -> bool:
    receiver = function.value
    return (
        isinstance(receiver, ast.Attribute)
        and receiver.attr == "read"
        and isinstance(receiver.value, ast.Name)
        and receiver.value.id == "spark"
    )


def _is_spark_table_call(function: ast.Attribute) -> bool:
    """Recognize batch and streaming Spark table calls."""
    receiver = function.value
    if isinstance(receiver, ast.Name) and receiver.id == "spark":
        return True
    if _is_spark_read_table(function):
        return True
    return (
        isinstance(receiver, ast.Attribute)
        and receiver.attr == "readStream"
        and isinstance(receiver.value, ast.Name)
        and receiver.value.id == "spark"
    )
