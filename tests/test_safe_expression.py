import pytest

from sdpstudio_codegen.safe_expression import validate_custom_dataframe_expression


def test_custom_dataframe_expression_accepts_typed_column_predicates() -> None:
    validate_custom_dataframe_expression(
        "df.filter(F.col('id') > F.lit(0)).select(F.upper(F.col('name')).alias('name'))"
    )
    validate_custom_dataframe_expression("df.where(F.col('id').isNotNull())")


@pytest.mark.parametrize(
    "expression",
    [
        "F.expr(\"reflect('java.lang.System','getenv','AWS_SECRET_ACCESS_KEY')\")",
        "df.selectExpr(\"java_method('java.lang.System','getProperty','user.name')\")",
        "df.filter(\"reflect('java.lang.System','getenv','AWS_SECRET_ACCESS_KEY')\")",
        "df.where(\"java_\" + \"method('java.lang.System','getProperty','user.name')\")",
        "F.input_file_name()",
        "F.call_function('reflect', F.lit('java.lang.System'))",
    ],
)
def test_custom_dataframe_expression_rejects_spark_sql_escape_hatches(expression: str) -> None:
    with pytest.raises(ValueError):
        validate_custom_dataframe_expression(expression)
