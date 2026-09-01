from sdpstudio_codegen import (
    generate_python_project,
    generate_sql_project,
    reconcile_python,
    reconcile_sql,
)
from sdpstudio_codegen.reconcile import parse_ownership_markers
from sdpstudio_core.models import Edge, Node, PipelineDocument


def doc() -> PipelineDocument:
    return PipelineDocument(
        pipelineId="reconcile-pipeline",
        nodes=[
            Node(id="source", type="source.table", config={"table": "orders"}),
            Node(id="filter", type="transform.filter", config={"expression": "amount > 0"}),
            Node(id="output", type="dataset.materialized_view", config={"name": "clean_orders"}),
        ],
        edges=[
            Edge(id="e1", **{"from": {"node": "source"}, "to": {"node": "filter", "port": "in"}}),
            Edge(id="e2", **{"from": {"node": "filter"}, "to": {"node": "output", "port": "in"}}),
        ],
    )


def test_supported_generated_expression_edit_reconciles_to_graph():
    source = generate_python_project(doc()).files[0].content.replace("amount > 0", "amount >= 10")
    result = reconcile_python(doc(), source)
    assert result.ownership == "visual"
    assert result.document.nodes[1].config["expression"] == "amount >= 10"
    assert any(region.ownership == "visual" for region in result.regions)


def test_unsupported_edit_is_reported_and_original_graph_is_preserved():
    source = (
        generate_python_project(doc())
        .files[0]
        .content.replace(
            "n_filter = n_source.filter(F.expr('amount > 0'))", "n_filter = custom_udf(n_source)"
        )
    )
    result = reconcile_python(doc(), source)
    assert result.ownership == "custom"
    assert result.document == doc()
    assert result.problems[0].code == "SDPS-RECON-003"
    assert any(region.ownership == "custom" for region in result.regions)


def test_supported_select_edit_reconciles_columns():
    document = doc().model_copy(
        update={
            "nodes": [
                *doc().nodes[:1],
                Node(id="select", type="transform.select", config={"columns": ["id"]}),
                doc().nodes[-1],
            ],
            "edges": [
                Edge(
                    id="e1", **{"from": {"node": "source"}, "to": {"node": "select", "port": "in"}}
                ),
                Edge(
                    id="e2", **{"from": {"node": "select"}, "to": {"node": "output", "port": "in"}}
                ),
            ],
        }
    )
    source = (
        generate_python_project(document)
        .files[0]
        .content.replace("F.expr('id')", "F.expr('id'), F.expr('amount')")
    )
    result = reconcile_python(document, source)
    assert result.ownership == "visual"
    assert result.document.nodes[1].config["columns"] == ["id", "amount"]


def test_supported_derive_rename_and_cast_edits_reconcile():
    for node_type, config, expected in [
        (
            "transform.derive",
            {"name": "total", "expression": "amount * 2"},
            {"name": "total", "expression": "amount * 2"},
        ),
        ("transform.rename", {"mapping": {"amount": "value"}}, {"mapping": {"amount": "value"}}),
        (
            "transform.cast",
            {"column": "amount", "dataType": "double"},
            {"column": "amount", "dataType": "double"},
        ),
    ]:
        document = doc().model_copy(
            update={
                "nodes": [
                    doc().nodes[0],
                    Node(id="transform", type=node_type, config=config),
                    doc().nodes[-1],
                ],
                "edges": [
                    Edge(
                        id="e1",
                        **{"from": {"node": "source"}, "to": {"node": "transform", "port": "in"}},
                    ),
                    Edge(
                        id="e2",
                        **{"from": {"node": "transform"}, "to": {"node": "output", "port": "in"}},
                    ),
                ],
            }
        )
        result = reconcile_python(document, generate_python_project(document).files[0].content)
        assert result.ownership == "visual"
        assert all(result.document.nodes[1].config[key] == value for key, value in expected.items())


def test_supported_drop_and_distinct_edits_reconcile():
    for node_type, config in [
        ("transform.drop", {"columns": ["obsolete"]}),
        ("transform.distinct", {}),
    ]:
        document = doc().model_copy(
            update={
                "nodes": [
                    doc().nodes[0],
                    Node(id="transform", type=node_type, config=config),
                    doc().nodes[-1],
                ],
                "edges": [
                    Edge(
                        id="e1",
                        **{"from": {"node": "source"}, "to": {"node": "transform", "port": "in"}},
                    ),
                    Edge(
                        id="e2",
                        **{"from": {"node": "transform"}, "to": {"node": "output", "port": "in"}},
                    ),
                ],
            }
        )
        result = reconcile_python(document, generate_python_project(document).files[0].content)
        assert result.ownership == "visual"


def test_supported_limit_edit_reconciles():
    document = doc().model_copy(
        update={
            "nodes": [
                doc().nodes[0],
                Node(id="limit", type="transform.limit", config={"count": 10}),
                doc().nodes[-1],
            ],
            "edges": [
                Edge(
                    id="e1", **{"from": {"node": "source"}, "to": {"node": "limit", "port": "in"}}
                ),
                Edge(
                    id="e2", **{"from": {"node": "limit"}, "to": {"node": "output", "port": "in"}}
                ),
            ],
        }
    )
    result = reconcile_python(document, generate_python_project(document).files[0].content)
    assert result.ownership == "visual"
    assert result.document.nodes[1].config["count"] == 10


def test_supported_sql_table_and_filter_edits_reconcile():
    source = (
        generate_sql_project(doc())
        .files[0]
        .content.replace("FROM orders", "FROM raw.orders")
        .replace("amount > 0", "amount >= 10")
    )
    result = reconcile_sql(doc(), source)
    assert result.ownership == "visual"
    assert result.document.nodes[0].config["table"] == "raw.orders"
    assert result.document.nodes[1].config["expression"] == "amount >= 10"


def test_supported_sql_limit_edit_reconciles():
    document = doc().model_copy(
        update={
            "nodes": [
                doc().nodes[0],
                Node(id="limit", type="transform.limit", config={"count": 10}),
                doc().nodes[-1],
            ],
            "edges": [
                Edge(
                    id="e1", **{"from": {"node": "source"}, "to": {"node": "limit", "port": "in"}}
                ),
                Edge(
                    id="e2", **{"from": {"node": "limit"}, "to": {"node": "output", "port": "in"}}
                ),
            ],
        }
    )
    result = reconcile_sql(document, generate_sql_project(document).files[0].content)
    assert result.ownership == "visual"
    assert result.document.nodes[1].config["count"] == 10


def test_unsupported_sql_shape_is_preserved_as_custom():
    result = reconcile_sql(doc(), "SELECT * FROM orders JOIN customers ON orders.id = customers.id")
    assert result.ownership == "custom"
    assert result.document == doc()
    assert result.problems[0].code.startswith("SDPS-RECON-")


def test_project_generated_python_round_trips_with_runtime_instrumentation(tmp_path):
    generated = generate_python_project(doc(), tmp_path).files[0].content
    result = reconcile_python(doc(), generated)
    assert result.ownership == "visual"
    assert not result.problems


def test_project_generation_emits_parseable_ownership_regions(tmp_path):
    generated = generate_python_project(doc(), tmp_path).files[0].content
    regions = parse_ownership_markers(generated)
    assert regions
    assert regions[0].node_id in {"source", "filter"}
    assert all(region.ownership == "visual" for region in regions)


def test_python_and_sql_generation_reconcile_and_regenerate_deterministically():
    document = doc()
    python_source = generate_python_project(document).files[0].content
    sql_source = generate_sql_project(document).files[0].content
    python_result = reconcile_python(document, python_source)
    sql_result = reconcile_sql(document, sql_source)
    assert python_result.ownership == sql_result.ownership == "visual"
    assert not python_result.problems and not sql_result.problems
    assert generate_python_project(python_result.document).files[0].content == python_source
    assert generate_sql_project(sql_result.document).files[0].content == sql_source


def test_level_b_four_branch_round_trip_acceptance_matrix():
    document = doc()
    generated = generate_python_project(document).files[0].content
    supported = reconcile_python(document, generated.replace("amount > 0", "amount >= 10"))
    unsupported = reconcile_python(
        document,
        generated.replace(
            "n_filter = n_source.filter(F.expr('amount > 0'))", "n_filter = custom_udf(n_source)"
        ),
    )
    regenerated = generate_python_project(supported.document).files[0].content
    assert supported.ownership == "visual"  # code -> visual
    assert regenerated == generated.replace("amount > 0", "amount >= 10")  # visual -> code
    assert (
        unsupported.ownership == "custom" and unsupported.document == document
    )  # custom preserved
    assert (
        reconcile_python(supported.document, regenerated).document == supported.document
    )  # deterministic round trip
