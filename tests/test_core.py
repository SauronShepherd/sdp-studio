import json
from pathlib import Path

import yaml
from sdpstudio_cli.main import build_parser, cmd_import_directory
from sdpstudio_codegen import generate_python_project
from sdpstudio_core import Result, utc_now
from sdpstudio_core.graph import GRAPH_PROBLEM_CODES, GraphIndex, validate_graph
from sdpstudio_core.ids import is_ulid, new_ulid
from sdpstudio_core.models import (
    Edge,
    EnvironmentReference,
    Node,
    Parameter,
    PipelineDocument,
    Port,
    PortRef,
    Position,
)


def sample_pipeline() -> PipelineDocument:
    source = Node(
        id=new_ulid(),
        type="source.table",
        position=Position(x=0, y=0),
        config={"table": "raw.orders", "streaming": False},
    )
    filt = Node(
        id=new_ulid(),
        type="transform.filter",
        position=Position(x=200, y=0),
        config={"expression": "status = 'COMPLETE'"},
    )
    select = Node(
        id=new_ulid(),
        type="transform.select",
        position=Position(x=400, y=0),
        config={"columns": ["order_id", "amount"]},
    )
    out = Node(
        id=new_ulid(),
        type="dataset.materialized_view",
        position=Position(x=600, y=0),
        config={"name": "complete_orders"},
    )
    return PipelineDocument(
        name="orders",
        nodes=[source, filt, select, out],
        edges=[
            Edge(
                **{
                    "from": PortRef(node=source.id, port="out"),
                    "to": PortRef(node=filt.id, port="in"),
                }
            ),
            Edge(
                **{
                    "from": PortRef(node=filt.id, port="out"),
                    "to": PortRef(node=select.id, port="in"),
                }
            ),
            Edge(
                **{
                    "from": PortRef(node=select.id, port="out"),
                    "to": PortRef(node=out.id, port="in"),
                }
            ),
        ],
    )


def test_ulid_shape():
    value = new_ulid()
    assert is_ulid(value)
    assert len(value) == 26


def test_graph_navigation_and_materialization_helpers_are_deterministic():
    document = sample_pipeline()
    index = GraphIndex(document)
    source, filt, select, output = [node.id for node in document.nodes]
    assert index.descendants(source) == {filt, select, output}
    assert index.ancestors(output) == {source, filt, select}
    assert index.connected_components() == [{source, filt, select, output}]
    assert index.materialization_boundaries() == {output}


def test_result_and_utc_clock_primitives():
    success = Result.success("ok")
    assert success.ok and success.value == "ok"
    assert utc_now().tzinfo is not None


def test_import_python_cli_is_registered():
    args = build_parser().parse_args(["import-python", "pipeline.py"])
    assert args.file == Path("pipeline.py")


def test_directory_import_cli_is_registered():
    args = build_parser().parse_args(
        ["import", "existing-project", "--name", "orders", "--visualize"]
    )
    assert args.directory == Path("existing-project")
    assert args.name == "orders"
    assert args.visualize is True


def test_directory_import_copies_source_without_mutating_it(tmp_path, monkeypatch, capsys):
    from sdpstudio_cli.main import cmd_import_directory

    source = tmp_path / "source"
    source.mkdir()
    (source / "transformations.py").write_text("# hand-authored\n", encoding="utf-8")
    before = (source / "transformations.py").read_bytes()
    monkeypatch.setenv("SDPSTUDIO_DATA_ROOT", str(tmp_path / "managed"))

    assert cmd_import_directory(type("Args", (), {"directory": source, "name": "orders"})()) == 0

    payload = json.loads(capsys.readouterr().out)
    assert (source / "transformations.py").read_bytes() == before
    managed = Path(payload["path"])
    assert (managed / ".sdpstudio" / "project.yaml").exists()
    assert (managed / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").exists()


def test_directory_import_visualize_discovers_python_and_sql(tmp_path, monkeypatch, capsys):
    source = tmp_path / "semantic-source"
    source.mkdir()
    (source / "pipeline.py").write_text(
        "from pyspark import pipelines as dp\n@dp.materialized_view(name='orders')\ndef orders():\n    return spark.table('raw.orders')\n",
        encoding="utf-8",
    )
    (source / "pipeline.sql").write_text(
        "CREATE MATERIALIZED VIEW events AS SELECT * FROM raw.events;\n", encoding="utf-8"
    )
    monkeypatch.setenv("SDPSTUDIO_DATA_ROOT", str(tmp_path / "managed"))
    assert (
        cmd_import_directory(
            type("Args", (), {"directory": source, "name": "semantic", "visualize": True})()
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["visualized"] is True
    report = Path(payload["path"]) / ".sdpstudio" / "import-report.json"
    assert report.exists()
    assert len(json.loads(report.read_text(encoding="utf-8"))["files"]) == 2
    imported = PipelineDocument.model_validate(
        yaml.safe_load(
            (Path(payload["path"]) / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    assert {node.config.get("table") for node in imported.nodes if node.type == "source.table"} == {
        "raw.events",
        "raw.orders",
    }
    assert len(imported.edges) == 2


def test_import_python_cli_reports_custom_code(tmp_path: Path, capsys):
    from sdpstudio_cli.main import cmd_import_python

    source = tmp_path / "custom.py"
    source.write_text("@dp.unknown()\ndef custom():\n    return 1\n", encoding="utf-8")
    assert cmd_import_python(type("Args", (), {"file": source})()) == 0
    assert '"custom_code"' in capsys.readouterr().out
    args = build_parser().parse_args(["generate", "project-id", "--target", "sql"])
    assert args.target == "sql"


def test_graph_topology_and_validation():
    doc = sample_pipeline()
    problems = validate_graph(doc)
    assert not [p for p in problems if p.severity == "error"]
    assert len(GraphIndex(doc).topological_order()) == 4


def test_graph_problem_code_registry_is_stable():
    assert GRAPH_PROBLEM_CODES["cycle_detected"] == "SDPS-GRAPH-001"
    assert GRAPH_PROBLEM_CODES["missing_input"] == "SDPS-GRAPH-002"
    assert GRAPH_PROBLEM_CODES["invalid_edge"] == "SDPS-GRAPH-003"
    assert GRAPH_PROBLEM_CODES["mode_incompatible"] == "SDPS-GRAPH-011"


def test_persisted_schema_entities_validate_typed_contracts_without_secrets():
    port = Port(name="in", direction="input", cardinality="many", modes=frozenset({"batch"}))
    parameter = Parameter(name="limit", data_type="integer", default=10)
    environment = EnvironmentReference(name="warehouse", variable="WAREHOUSE_URL", required=True)
    assert port.cardinality == "many"
    assert parameter.default == 10
    assert environment.variable == "WAREHOUSE_URL"


def test_graph_validation_rejects_streaming_input_to_batch_only_operator():
    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={"streaming": False}),
            Node(
                id="aggregate",
                type="dataset.auto_cdc_scd1",
                config={"name": "events", "keys": ["id"], "sequence_by": "ts"},
            ),
        ],
        edges=[Edge(id="e1", **{"from": {"node": "source"}, "to": {"node": "aggregate"}})],
    )
    problems = validate_graph(document)
    assert any(problem.code == "SDPS-GRAPH-011" for problem in problems)


def test_graph_validation_uses_operator_registry_contract():
    doc = sample_pipeline()
    doc.nodes[1].config = {}
    problems = validate_graph(doc)
    assert any(p.code == "SDPS-OPERATOR-001" and p.node_id == doc.nodes[1].id for p in problems)


def test_codegen_is_deterministic(tmp_path: Path):
    doc = sample_pipeline()
    first = generate_python_project(doc, tmp_path)
    second = generate_python_project(doc, tmp_path)
    assert first.files == second.files
    code = first.files[0].content
    assert "from pyspark import pipelines as dp" in code
    assert "@dp.materialized_view(name='complete_orders')" in code
    assert (
        ".filter(F.expr(\"status = 'COMPLETE'\"))" in code
        or ".filter(F.expr('status = \\'COMPLETE\\''))" in code
    )
    assert "return n_" in code
    assert len(first.source_map) == 4


def test_codegen_allows_runtime_storage_uri_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_STORAGE_URI", "file:///mnt/shared/storage")
    monkeypatch.setenv("SDPSTUDIO_EVENT_LOG_URI", "file:///mnt/shared/event-logs")
    result = generate_python_project(sample_pipeline(), tmp_path)
    spec = next(file.content for file in result.files if file.path == "spark-pipeline.yaml")
    assert "storage: file:///mnt/shared/storage" in spec
    assert 'spark.eventLog.dir: "file:///mnt/shared/event-logs"' in spec


def test_streaming_to_materialized_is_rejected(tmp_path: Path):
    doc = sample_pipeline()
    doc.nodes[0].config["streaming"] = True
    result = generate_python_project(doc, tmp_path)
    assert not result.files
    assert any(p.code == "SDPS-SDP-001" for p in result.problems)


def test_cycle_is_reported():
    doc = sample_pipeline()
    doc.edges.append(
        Edge(
            **{
                "from": PortRef(node=doc.nodes[2].id, port="out"),
                "to": PortRef(node=doc.nodes[1].id, port="in"),
            }
        )
    )
    problems = validate_graph(doc)
    assert any(p.code == "SDPS-GRAPH-001" for p in problems)


def test_secret_literals_are_rejected_and_refs_codegen(tmp_path: Path):
    doc = sample_pipeline()
    doc.nodes[0].type = "source.jdbc"
    doc.nodes[0].config = {
        "url": "jdbc:postgresql://db/app",
        "dbtable": "orders",
        "options": {"password": "super-secret-password"},
    }
    assert any(p.code == "SDPS-SEC-001" for p in validate_graph(doc))

    doc.nodes[0].config["options"]["password"] = "secret://JDBC_PASSWORD"
    result = generate_python_project(doc, tmp_path)
    assert not [p for p in result.problems if p.severity == "error"]
    assert "import os" in result.files[0].content
    assert "os.environ['JDBC_PASSWORD']" in result.files[0].content


def test_portable_source_operators_generate_deterministically():
    reference = Node(type="source.dataset_reference", config={"name": "bronze", "streaming": True})
    output = Node(type="dataset.streaming_table", config={"name": "silver"})
    doc = PipelineDocument(
        nodes=[reference, output],
        edges=[
            Edge(**{"from": PortRef(node=reference.id), "to": PortRef(node=output.id, port="in")})
        ],
    )
    result = generate_python_project(doc)
    assert not result.problems
    assert "spark.readStream.table('bronze')" in result.files[0].content


def test_dataset_chaining_references_declared_dataset(tmp_path: Path):
    source = Node(type="source.table", config={"table": "raw.orders", "streaming": False})
    bronze = Node(type="dataset.materialized_view", config={"name": "bronze_orders"})
    filt = Node(type="transform.filter", config={"expression": "amount > 100"})
    silver = Node(type="dataset.materialized_view", config={"name": "silver_orders"})
    doc = PipelineDocument(
        name="medallion",
        nodes=[source, bronze, filt, silver],
        edges=[
            Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=bronze.id, port="in")}),
            Edge(**{"from": PortRef(node=bronze.id), "to": PortRef(node=filt.id, port="in")}),
            Edge(**{"from": PortRef(node=filt.id), "to": PortRef(node=silver.id, port="in")}),
        ],
    )
    result = generate_python_project(doc, tmp_path)
    assert not [p for p in result.problems if p.severity == "error"]
    code = result.files[0].content
    assert "@dp.materialized_view(name='bronze_orders')" in code
    assert "@dp.materialized_view(name='silver_orders')" in code
    silver_block = code.split("@dp.materialized_view(name='silver_orders')", 1)[1]
    assert "spark.table('bronze_orders')" in silver_block
    assert "spark.table('raw.orders')" not in silver_block


def test_streaming_sink_codegen(tmp_path: Path):
    source = Node(
        type="source.kafka",
        config={"bootstrapServers": "kafka:9092", "subscribe": "orders", "options": {}},
    )
    sink = Node(
        type="sink.external",
        config={"name": "processed_orders", "format": "kafka", "options": {"topic": "processed"}},
    )
    doc = PipelineDocument(
        name="sink-test",
        nodes=[source, sink],
        edges=[Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=sink.id, port="in")})],
    )
    result = generate_python_project(doc, tmp_path)
    assert not [p for p in result.problems if p.severity == "error"]
    code = result.files[0].content
    assert (
        "dp.create_sink(name='processed_orders', format='kafka', options={'topic': 'processed'})"
        in code
    )
    assert "@dp.append_flow(target='processed_orders', name='flow_processed_orders')" in code


def test_batch_sink_is_rejected(tmp_path: Path):
    source = Node(type="source.table", config={"table": "raw.orders", "streaming": False})
    sink = Node(
        type="sink.external",
        config={"name": "bad_sink", "format": "parquet", "options": {"path": "/tmp/out"}},
    )
    doc = PipelineDocument(
        name="sink-test",
        nodes=[source, sink],
        edges=[Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=sink.id, port="in")})],
    )
    result = generate_python_project(doc, tmp_path)
    assert any(p.code == "SDPS-SDP-003" for p in result.problems)


def test_json_and_window_codegen(tmp_path: Path):
    source = Node(type="source.table", config={"table": "raw.events"})
    parsed = Node(
        type="transform.json_parse",
        config={"column": "payload", "schema": "id INT", "target": "payload_struct"},
    )
    window = Node(
        type="transform.window",
        config={
            "target": "row_number",
            "expression": "row_number()",
            "partitionBy": ["id"],
            "orderBy": ["event_ts"],
        },
    )
    output = Node(type="dataset.materialized_view", config={"name": "parsed_events"})
    edges = [
        Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=parsed.id, port="in")}),
        Edge(**{"from": PortRef(node=parsed.id), "to": PortRef(node=window.id, port="in")}),
        Edge(**{"from": PortRef(node=window.id), "to": PortRef(node=output.id, port="in")}),
    ]
    result = generate_python_project(
        PipelineDocument(nodes=[source, parsed, window, output], edges=edges), tmp_path
    )
    assert not [problem for problem in result.problems if problem.severity == "error"]
    assert "from pyspark.sql.window import Window" in result.files[0].content
    assert "F.from_json" in result.files[0].content
