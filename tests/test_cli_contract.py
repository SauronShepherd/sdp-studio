import json
from argparse import Namespace
from pathlib import Path
from zipfile import ZipFile

from sdpstudio_cli.main import (
    build_parser,
    cmd_debug_bundle,
    cmd_generate,
    cmd_history,
    cmd_import_directory,
    cmd_init,
    cmd_version,
)


def test_cli_registers_init_and_version() -> None:
    parser = build_parser()
    assert parser.parse_args(["version"]).command == "version"
    assert parser.parse_args(["init", "project"]).command == "init"
    assert parser.parse_args(["history", "list", "project-id"]).history_command == "list"
    assert (
        parser.parse_args(["history", "restore", "project-id", "snapshot-id"]).history_command
        == "restore"
    )
    assert parser.parse_args(["debug", "bundle", "run-id"]).debug_command == "bundle"
    assert parser.parse_args(["validate", "project-id", "--runtime", "local"]).runtime == "local"
    assert parser.parse_args(["import", "directory", "--report-only"]).report_only is True
    assert parser.parse_args(["worker", "--runs-only"]).runs_only is True


def test_init_creates_directory_local_project_without_database(tmp_path: Path) -> None:
    target = tmp_path / "orders"
    assert cmd_init(Namespace(directory=target, name="orders")) == 0
    assert (target / ".sdpstudio" / "project.yaml").exists()
    assert (target / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").exists()
    assert (target / "transformations").is_dir()


def test_init_refuses_nonempty_directory(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "README.md").write_text("existing", encoding="utf-8")
    assert cmd_init(Namespace(directory=target, name=None)) == 2


def test_version_command_succeeds(capsys) -> None:
    assert cmd_version(Namespace()) == 0
    assert capsys.readouterr().out.startswith("sdpstudio ")


def test_directory_import_persists_visual_graph_by_default(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pipeline.py").write_text(
        "import pyspark.pipelines as dp\n\n@dp.table\ndef orders():\n    return spark.read.table('raw.orders')\n",
        encoding="utf-8",
    )

    class FakeStore:
        def __init__(self):
            self.saved = None
            self.project = {
                "id": "project-1",
                "name": "imported",
                "path": str(tmp_path / "project"),
            }

        def create_project(self, name, example_path=None):
            return {**self.project, "name": name}

        def save_pipeline(self, project_id, document):
            self.saved = (project_id, document)

    fake = FakeStore()
    monkeypatch.setattr("sdpstudio_cli.main._store", lambda: fake)
    assert (
        cmd_import_directory(
            Namespace(directory=source, name="imported", report_only=False, visualize=False)
        )
        == 0
    )
    assert fake.saved is not None
    assert fake.saved[1].nodes
    assert json.loads(capsys.readouterr().out)["visualized"] is True


def test_directory_import_report_only_does_not_persist_graph(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pipeline.py").write_text(
        "import pyspark.pipelines as dp\n@dp.table\ndef orders():\n    return spark.read.table('raw.orders')\n",
        encoding="utf-8",
    )

    class Store:
        def __init__(self):
            self.saved = False

        def create_project(self, name, example_path=None):
            return {"id": "project-1", "name": name, "path": str(tmp_path / "project")}

        def save_pipeline(self, project_id, document):
            self.saved = True

    store = Store()
    monkeypatch.setattr("sdpstudio_cli.main._store", lambda: store)
    assert (
        cmd_import_directory(
            Namespace(directory=source, name="imported", report_only=True, visualize=False)
        )
        == 0
    )
    assert store.saved is False
    assert json.loads(capsys.readouterr().out)["visualized"] is False


def test_history_list_and_restore_use_storage_contract(monkeypatch, capsys) -> None:
    class Store:
        def list_history(self, project_id):
            return [{"id": "snapshot-1", "revision": 1, "project": project_id}]

        def restore_history(self, project_id, snapshot_id):
            from sdpstudio_core.models import PipelineDocument

            return PipelineDocument(pipelineId=snapshot_id, name=project_id)

    monkeypatch.setattr("sdpstudio_cli.main._store", lambda: Store())
    assert cmd_history(type("Args", (), {"history_command": "list", "project_id": "p"})()) == 0
    assert "snapshot-1" in capsys.readouterr().out
    assert (
        cmd_history(
            type(
                "Args", (), {"history_command": "restore", "project_id": "p", "snapshot_id": "s"}
            )()
        )
        == 0
    )
    assert '"pipelineId": "s"' in capsys.readouterr().out


def test_debug_bundle_cli_uses_redacted_bundle_builder(monkeypatch, tmp_path: Path) -> None:
    class Store:
        def get_run(self, run_id):
            return {"id": run_id, "project_id": "p", "status": "succeeded"}

        def project_path(self, _project_id):
            return tmp_path / "project"

        def run_events(self, _run_id):
            return []

        def get_node_snapshots(self, _run_id):
            return []

        def list_secrets(self):
            return []

    output = tmp_path / "debug.zip"
    monkeypatch.setattr("sdpstudio_cli.main._store", lambda: Store())
    assert cmd_debug_bundle(type("Args", (), {"run_id": "run-1", "output": output})()) == 0
    with ZipFile(output) as archive:
        assert {"README.txt", "run.json", "manifest.json"} <= set(archive.namelist())


def test_generate_check_uses_persisted_sql_service_and_detects_source_map_drift(
    monkeypatch, tmp_path: Path
):
    import hashlib
    from types import SimpleNamespace

    project = tmp_path / "project"
    (project / "transformations").mkdir(parents=True)
    (project / ".sdpstudio" / "source-maps").mkdir(parents=True)
    content = "SELECT 1;\n"
    generated = project / "transformations" / "generated.sql"
    generated.write_text(content, encoding="utf-8")
    (project / ".sdpstudio" / "source-maps" / "generated.sql.map.json").write_text(
        '{\n  "schemaVersion": 1,\n  "mappings": [],\n  "files": {\n'
        f'    "transformations/generated.sql": "{hashlib.sha256(generated.read_bytes()).hexdigest()}"\n'
        "  }\n}\n",
        encoding="utf-8",
    )

    class Store:
        def project_path(self, _project_id):
            return project

        def generate_sql(self, _project_id, write):
            assert write is False
            return SimpleNamespace(
                problems=[],
                files=[
                    SimpleNamespace(
                        path="transformations/generated.sql",
                        content=content,
                        sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
                    )
                ],
                source_map=[],
            )

    monkeypatch.setattr("sdpstudio_cli.main._store", lambda: Store())
    assert cmd_generate(Namespace(project_id="p", target="sql", check=True, stdout=False)) == 0

    (project / ".sdpstudio" / "source-maps" / "generated.sql.map.json").write_text(
        "{}\n", encoding="utf-8"
    )
    assert cmd_generate(Namespace(project_id="p", target="sql", check=True, stdout=False)) == 1
