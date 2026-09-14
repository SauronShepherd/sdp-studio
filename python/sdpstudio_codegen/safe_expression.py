"""Fail-closed AST policy for visual custom-code dataframe expressions."""

from __future__ import annotations

import ast

_ALLOWED_NAMES = {"df", "F"}
_ALLOWED_DATAFRAME_METHODS = {
    "alias",
    "coalesce",
    "crossJoin",
    "distinct",
    "drop",
    "dropDuplicates",
    "filter",
    "join",
    "limit",
    "orderBy",
    "repartition",
    "sample",
    "select",
    "sort",
    "union",
    "unionByName",
    "where",
    "withColumn",
    "withColumnRenamed",
}
_ALLOWED_COLUMN_METHODS = {
    "alias",
    "asc",
    "asc_nulls_first",
    "asc_nulls_last",
    "between",
    "cast",
    "contains",
    "desc",
    "desc_nulls_first",
    "desc_nulls_last",
    "endswith",
    "eqNullSafe",
    "isNotNull",
    "isNull",
    "isin",
    "otherwise",
    "startswith",
    "when",
}
# These APIs cross from typed Column construction back into dynamic SQL/code
# interpretation or runtime-defined functions. Keep them closed even though
# they are public members of pyspark.sql.functions.
_BLOCKED_FUNCTIONS = {
    "call_function",
    "call_udf",
    "expr",
    "input_file_name",
    "java_method",
    "pandas_udf",
    "reflect",
    "udf",
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.keyword,
    ast.BinOp,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Subscript,
    ast.Slice,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    ast.USub,
    ast.UAdd,
    ast.Invert,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)


def _is_dataframe_column_subscript(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "df"
    )


def _contains_typed_column(node: ast.AST) -> bool:
    """Return whether an expression is rooted in a typed Spark Column value."""
    return any(
        _is_dataframe_column_subscript(nested)
        or (isinstance(nested, ast.Call) and _call_kind(nested) == "column")
        for nested in ast.walk(node)
    )


def _predicate_argument(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    return next(
        (keyword.value for keyword in node.keywords if keyword.arg == "condition"),
        None,
    )


def _validate_dataframe_call(node: ast.Call, method: str) -> None:
    if method not in {"filter", "where"}:
        return
    predicate = _predicate_argument(node)
    if predicate is None or not _contains_typed_column(predicate):
        raise ValueError(
            f"DataFrame.{method} requires a typed Column predicate; Spark SQL strings are not allowed"
        )


def _call_kind(node: ast.Call) -> str:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr.startswith("_"):
        raise ValueError(
            "Custom code calls must use public DataFrame or pyspark.sql.functions APIs"
        )
    if isinstance(func.value, ast.Name):
        if func.value.id == "F":
            if func.attr in _BLOCKED_FUNCTIONS:
                raise ValueError(f"pyspark.sql.functions call is not allowed: F.{func.attr}")
            return "column"
        if func.value.id == "df" and func.attr in _ALLOWED_DATAFRAME_METHODS:
            _validate_dataframe_call(node, func.attr)
            return "dataframe"
        raise ValueError(f"Custom code call is not allowed: {ast.unparse(func)}")
    if isinstance(func.value, ast.Call):
        parent_kind = _call_kind(func.value)
        allowed = (
            _ALLOWED_DATAFRAME_METHODS if parent_kind == "dataframe" else _ALLOWED_COLUMN_METHODS
        )
        if func.attr not in allowed:
            raise ValueError(f"Custom code chained call is not allowed: {func.attr}")
        if parent_kind == "dataframe":
            _validate_dataframe_call(node, func.attr)
            return "dataframe"
        return "column"
    raise ValueError("Custom code call receiver is not allowed")


def validate_custom_dataframe_expression(expression: str) -> None:
    """Accept only expression-only public Spark DataFrame/Column construction.

    The generated module already provides ``df`` and ``F``. Arbitrary Python
    names, imports, lambdas, comprehensions, private attributes, dynamic SQL,
    runtime-defined functions and host-side calls are rejected before code
    generation.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Custom code must be one valid Python expression") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Custom code syntax is not allowed: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
            raise ValueError(f"Custom code name is not allowed: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("Custom code private attributes are not allowed")
        if isinstance(node, ast.Call):
            _call_kind(node)
