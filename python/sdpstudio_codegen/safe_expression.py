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
# Keep this list intentionally explicit. Functions that parse arbitrary SQL,
# invoke JVM methods/UDFs, or expose input paths are not part of this boundary.
_ALLOWED_FUNCTIONS = {
    "abs",
    "acos",
    "array",
    "array_contains",
    "array_distinct",
    "array_except",
    "array_intersect",
    "array_join",
    "array_max",
    "array_min",
    "array_position",
    "array_remove",
    "array_repeat",
    "array_size",
    "array_sort",
    "arrays_overlap",
    "arrays_zip",
    "asc",
    "asin",
    "atan",
    "atan2",
    "avg",
    "base64",
    "bround",
    "ceil",
    "ceiling",
    "coalesce",
    "col",
    "collect_list",
    "collect_set",
    "concat",
    "concat_ws",
    "corr",
    "cos",
    "cosh",
    "count",
    "count_distinct",
    "countDistinct",
    "covar_pop",
    "covar_samp",
    "crc32",
    "create_map",
    "current_date",
    "current_timestamp",
    "date_add",
    "date_format",
    "date_sub",
    "datediff",
    "dayofmonth",
    "dayofweek",
    "dayofyear",
    "desc",
    "element_at",
    "exp",
    "first",
    "first_value",
    "flatten",
    "floor",
    "greatest",
    "hash",
    "hour",
    "instr",
    "isnan",
    "isnull",
    "last",
    "last_day",
    "last_value",
    "least",
    "length",
    "lit",
    "log",
    "log10",
    "log1p",
    "lower",
    "lpad",
    "ltrim",
    "map_concat",
    "map_contains_key",
    "map_entries",
    "map_from_arrays",
    "map_from_entries",
    "map_keys",
    "map_values",
    "max",
    "max_by",
    "md5",
    "mean",
    "median",
    "min",
    "min_by",
    "minute",
    "mode",
    "month",
    "months_between",
    "nanvl",
    "next_day",
    "percentile",
    "percentile_approx",
    "pow",
    "power",
    "quarter",
    "radians",
    "regexp_extract",
    "regexp_extract_all",
    "regexp_replace",
    "repeat",
    "replace",
    "round",
    "rpad",
    "rtrim",
    "second",
    "sha1",
    "sha2",
    "size",
    "slice",
    "sort_array",
    "split",
    "sqrt",
    "stddev",
    "stddev_pop",
    "stddev_samp",
    "struct",
    "substring",
    "substring_index",
    "sum",
    "sum_distinct",
    "tan",
    "tanh",
    "to_date",
    "to_timestamp",
    "translate",
    "trim",
    "trunc",
    "unix_date",
    "unbase64",
    "upper",
    "var_pop",
    "var_samp",
    "variance",
    "when",
    "xxhash64",
    "year",
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


def _is_python_string_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return _is_python_string_expression(node.left) and _is_python_string_expression(node.right)
    return False


def _validate_dataframe_call(node: ast.Call, method: str) -> None:
    if method not in {"filter", "where"}:
        return
    if len(node.args) != 1 or node.keywords:
        raise ValueError(f"Custom code {method}() must receive exactly one Column predicate")
    if _is_python_string_expression(node.args[0]):
        raise ValueError(
            f"Custom code {method}() does not accept Spark SQL strings; build a Column expression instead"
        )


def _call_kind(node: ast.Call) -> str:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr.startswith("_"):
        raise ValueError(
            "Custom code calls must use public DataFrame or pyspark.sql.functions APIs"
        )
    if isinstance(func.value, ast.Name):
        if func.value.id == "F":
            if func.attr not in _ALLOWED_FUNCTIONS:
                raise ValueError(f"Custom code Spark function is not allowed: F.{func.attr}")
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
        return "dataframe" if parent_kind == "dataframe" else "column"
    raise ValueError("Custom code call receiver is not allowed")


def validate_custom_dataframe_expression(expression: str) -> None:
    """Accept only expression-only public Spark DataFrame/Column construction.

    The generated module already provides ``df`` and ``F``. Arbitrary Python
    names, imports, lambdas, comprehensions, private attributes, Spark SQL
    string expressions, and host-side function calls are rejected before code
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
