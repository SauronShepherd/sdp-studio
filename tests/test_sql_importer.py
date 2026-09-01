from pathlib import Path

from sdpstudio_codegen import discover_sql


def test_sql_importer_discovers_supported_declarations(tmp_path: Path):
    report = discover_sql(
        tmp_path / "pipeline.sql",
        "CREATE MATERIALIZED VIEW orders AS SELECT * FROM raw.orders;\nCREATE STREAMING TABLE events AS SELECT * FROM raw.events;",
    )
    assert [(item.name, item.kind) for item in report.declarations] == [
        ("orders", "dataset.materialized_view"),
        ("events", "dataset.streaming_table"),
    ]
    assert report.declarations[0].dependencies == ("raw.orders",)
    assert report.declarations[1].dependencies == ("raw.events",)


def test_sql_importer_preserves_code_owned_statements(tmp_path: Path):
    source = "CREATE TEMP VIEW orders AS SELECT 1;\nINSERT INTO audit SELECT * FROM orders;\n"
    report = discover_sql(tmp_path / "custom.sql", source)
    assert report.custom_code[0].source == source
    assert len(report.source_sha256) == 64


def test_sql_importer_uses_parser_for_ctes_aliases_and_joins(tmp_path: Path):
    source = """CREATE MATERIALIZED VIEW orders AS
WITH recent AS (SELECT * FROM raw.orders)
SELECT r.* FROM recent AS r JOIN raw.customers AS c ON r.customer_id = c.id;
"""
    report = discover_sql(tmp_path / "parsed.sql", source)
    assert report.declarations[0].dependencies == ("raw.customers", "raw.orders")


def test_sql_importer_uses_sqlglot_fallback_for_standard_create_view(tmp_path: Path):
    report = discover_sql(
        tmp_path / "standard.sql", "CREATE VIEW orders AS SELECT * FROM raw.orders;"
    )
    assert [(item.name, item.kind) for item in report.declarations] == [
        ("orders", "dataset.materialized_view")
    ]
    assert report.declarations[0].dependencies == ("raw.orders",)
