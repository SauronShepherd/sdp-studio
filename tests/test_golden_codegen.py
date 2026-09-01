from pathlib import Path

from sdpstudio_codegen import generate_python_project, generate_sql_project
from sdpstudio_core.models import Edge, Node, PipelineDocument

GOLDEN = Path(__file__).parent / "golden" / "python_basic_generated.py"
SQL_GOLDEN = Path(__file__).parent / "golden" / "sql_basic_generated.sql"


def _document() -> PipelineDocument:
    return PipelineDocument(
        pipelineId="golden-pipeline",
        name="golden_orders",
        nodes=[
            Node(id="source", type="source.table", config={"table": "orders"}),
            Node(id="filter", type="transform.filter", config={"expression": "amount > 0"}),
            Node(
                id="output",
                type="dataset.materialized_view",
                config={"name": "clean_orders"},
            ),
        ],
        edges=[
            Edge(id="e1", **{"from": {"node": "source"}, "to": {"node": "filter", "port": "in"}}),
            Edge(id="e2", **{"from": {"node": "filter"}, "to": {"node": "output", "port": "in"}}),
        ],
    )


def test_python_codegen_matches_reviewed_golden_source() -> None:
    result = generate_python_project(_document())

    assert not result.problems
    generated = next(file for file in result.files if file.path == "transformations/generated.py")
    expected = GOLDEN.read_text(encoding="utf-8")

    assert generated.content == expected
    assert generated.sha256 == "4c061197394ae4319bc69495cd2aa9f574353124143e576a2b44966fe45b16b2"


def test_python_codegen_is_stable_across_repeated_generation() -> None:
    first = generate_python_project(_document())
    second = generate_python_project(_document())

    assert [(file.path, file.content, file.sha256) for file in first.files] == [
        (file.path, file.content, file.sha256) for file in second.files
    ]


def test_sql_codegen_matches_reviewed_golden_source() -> None:
    result = generate_sql_project(_document())
    assert not result.problems
    generated = next(file for file in result.files if file.path == "transformations/generated.sql")
    assert generated.content == SQL_GOLDEN.read_text(encoding="utf-8")


def test_sql_codegen_is_stable_across_repeated_generation() -> None:
    first = generate_sql_project(_document())
    second = generate_sql_project(_document())
    assert [(file.path, file.content, file.sha256) for file in first.files] == [
        (file.path, file.content, file.sha256) for file in second.files
    ]


def test_event_time_deduplication_is_supported_and_deterministic() -> None:
    document = PipelineDocument(
        pipelineId="dedup-pipeline",
        name="dedup_orders",
        nodes=[
            Node(id="source", type="source.table", config={"table": "orders"}),
            Node(
                id="dedup",
                type="transform.deduplicate_event_time",
                config={
                    "columns": ["order_id"],
                    "eventTime": "updated_at",
                    "watermark": "5 minutes",
                },
            ),
            Node(id="output", type="dataset.materialized_view", config={"name": "latest_orders"}),
        ],
        edges=[
            Edge(id="e1", **{"from": {"node": "source"}, "to": {"node": "dedup", "port": "in"}}),
            Edge(id="e2", **{"from": {"node": "dedup"}, "to": {"node": "output", "port": "in"}}),
        ],
    )
    python_result = generate_python_project(document)
    sql_result = generate_sql_project(document)
    assert not python_result.problems
    assert not sql_result.problems
    python_source = next(
        file.content for file in python_result.files if file.path.endswith("generated.py")
    )
    sql_source = next(
        file.content for file in sql_result.files if file.path.endswith("generated.sql")
    )
    assert "withWatermark('updated_at', '5 minutes').dropDuplicates(['order_id'])" in python_source
    assert "ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC)" in sql_source
