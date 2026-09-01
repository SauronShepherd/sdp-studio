from pathlib import Path

from sdpstudio_codegen import discover_python, source_changed, source_hash


def test_python_importer_discovers_declarations_without_execution(tmp_path: Path):
    source = """\
from pyspark import pipelines as dp
raise RuntimeError('must never execute')
@dp.materialized_view(name='orders')
def orders():
    return spark.table('raw.orders')
@dp.table()
def events():
    return spark.readStream.table('raw.events')
"""
    report = discover_python(tmp_path / "pipeline.py", source)
    assert [(item.name, item.kind) for item in report.declarations] == [
        ("orders", "dataset.materialized_view"),
        ("events", "dataset.streaming_table"),
    ]
    assert report.declarations[0].dependencies == ("raw.orders",)
    assert len(report.source_sha256) == 64
    assert source_changed(report.source_sha256, source) is False
    assert source_changed(source_hash(source), source + "\n# edited") is True
    assert report.declarations[0].start_line == 4


def test_python_importer_flags_dynamic_spark_read_table_dependency(tmp_path: Path):
    source = """from pyspark import pipelines as dp
@dp.materialized_view(name='orders')
def orders():
    return spark.read.table('raw.orders')
"""
    report = discover_python(tmp_path / "pipeline.py", source)
    assert report.declarations[0].dependencies == ("raw.orders",)

    dynamic = source.replace("'raw.orders'", "table_name")
    dynamic_report = discover_python(tmp_path / "pipeline.py", dynamic)
    assert "dynamic_dependency" in dynamic_report.unsupported

    direct_dynamic = source.replace("spark.read.table('raw.orders')", "spark.table(table_name)")
    direct_report = discover_python(tmp_path / "pipeline.py", direct_dynamic)
    assert "dynamic_dependency" in direct_report.unsupported


def test_python_importer_handles_streaming_dynamic_dependency_and_auto_cdc(tmp_path: Path):
    source = """from pyspark import pipelines as dp
@dp.create_auto_cdc_flow(target='customers', keys=['id'], sequence_by='updated_at')
def customers_flow():
    return spark.readStream.table(table_name)
"""
    report = discover_python(tmp_path / "cdc.py", source)
    assert report.declarations[0].kind == "dataset.auto_cdc_scd1"
    assert "dynamic_dependency" in report.unsupported


def test_python_importer_preserves_unsupported_code_verbatim(tmp_path: Path):
    source = "from pyspark import pipelines as dp\n@dp.unknown()\ndef custom():\n    return spark.sql('select 1')\n"
    report = discover_python(tmp_path / "custom.py", source)
    assert report.custom_code[0].source == source
    assert report.custom_code[0].source_sha256 == source_hash(source)


def test_python_importer_discovers_call_style_sdp_declarations(tmp_path: Path):
    source = """from pyspark import pipelines as dp
dp.create_streaming_table(name='events')
dp.create_sink(name='warehouse_sink', format='delta')
dp.create_auto_cdc_flow(target='customers', keys=['id'], sequence_by='updated_at')
"""
    report = discover_python(tmp_path / "calls.py", source)
    assert [(item.name, item.kind) for item in report.declarations] == [
        ("events", "dataset.streaming_table"),
        ("warehouse_sink", "sink.external"),
        ("customers", "dataset.auto_cdc_scd1"),
    ]


def test_python_importer_uses_auto_cdc_target_as_declaration_name(tmp_path: Path):
    source = """from pyspark import pipelines as dp
@dp.create_auto_cdc_flow(target='customers', keys=['id'], sequence_by='updated_at')
def generated_flow():
    return spark.readStream.table('raw.customers')
"""
    report = discover_python(tmp_path / "cdc.py", source)
    assert report.declarations[0].name == "customers"
    assert report.declarations[0].kind == "dataset.auto_cdc_scd1"
