import pytest
from sdpstudio_codegen.safe_expression import validate_custom_dataframe_expression


@pytest.mark.parametrize(
    "expression",
    [
        'df.filter(F.col("status") == F.lit("ACTIVE")).select(F.col("id"))',
        'df.where((F.col("amount") > 0) & F.col("customer_id").isNotNull())',
        'df.filter(df["amount"] > 0)',
    ],
)
def test_typed_dataframe_expressions_remain_allowed(expression: str) -> None:
    validate_custom_dataframe_expression(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "F.expr(\"reflect('java.lang.System','getenv','AWS_SECRET_ACCESS_KEY')\")",
        "df.selectExpr(\"java_method('java.lang.System','getProperty','user.name')\")",
        'df.filter("id > 0")',
        'df.where("id " + "> 0")',
        (
            'F.call_function("reflect", F.lit("java.lang.System"), '
            'F.lit("getenv"), F.lit("AWS_SECRET_ACCESS_KEY"))'
        ),
    ],
)
def test_dynamic_sql_and_runtime_function_escapes_are_rejected(expression: str) -> None:
    with pytest.raises(ValueError):
        validate_custom_dataframe_expression(expression)
