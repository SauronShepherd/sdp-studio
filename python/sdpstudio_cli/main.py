from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import webbrowser
import zipfile
from pathlib import Path

import uvicorn
from sdpstudio_codegen import discover_python, discover_sql
from sdpstudio_core.capabilities import validate_capabilities
from sdpstudio_core.graph import validate_graph
from sdpstudio_core.models import Edge, Node, PipelineDocument, Problem, ProjectMetadata
from sdpstudio_runners.local import LocalRuntime, probe_local
from sdpstudio_runners.profiles import build_run_command, probe_profile
from sdpstudio_server.app import _redact_bundle_value, _redact_registered_secrets, create_app
from sdpstudio_server.debug_bundle_service import build_entries
from sdpstudio_server.run_worker import DurableRunWorker, execute_queued_local_run
from sdpstudio_server.scheduler import ScheduleWorker
from sdpstudio_server.storage import DataStore, atomic_write, yaml_dump


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _example_path(name: str) -> Path:
    source = _repo_root() / "examples" / name
    if source.exists():
        return source
    packaged = Path(__file__).resolve().parents[1] / "sdpstudio_server" / "examples" / name
    return packaged


def _store() -> DataStore:
    return DataStore()


def cmd_version(_args: argparse.Namespace) -> int:
    try:
        version = importlib.metadata.version("sdpstudio")
    except importlib.metadata.PackageNotFoundError:
        version = "0.1.0"
    print(f"sdpstudio {version}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    directory = args.directory.expanduser().resolve()
    if directory.exists() and any(directory.iterdir()):
        print(f"Directory is not empty: {directory}", file=sys.stderr)
        return 2
    directory.mkdir(parents=True, exist_ok=True)
    name = args.name or directory.name
    document = PipelineDocument(name=name)
    metadata = ProjectMetadata(
        name=name,
        pipelines=[
            {"id": document.pipelineId, "model": ".sdpstudio/pipelines/main.sdpstudio.yaml"}
        ],
    )
    pipeline_path = directory / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml"
    atomic_write(directory / ".sdpstudio" / "project.yaml", yaml_dump(metadata.model_dump()))
    atomic_write(pipeline_path, yaml_dump(document.model_dump(by_alias=True)))
    (directory / "transformations").mkdir(parents=True, exist_ok=True)
    atomic_write(directory / ".gitignore", ".sdpstudio/runtime/\n.sdpstudio/history/\n")
    print(str(directory))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    result = probe_local().model_dump()
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("SDP Studio local runtime doctor")
        print(f"  available:       {result['available']}")
        print(f"  Spark version:   {result.get('spark_version') or 'not detected'}")
        for key, value in result["details"].items():
            print(f"  {key:18} {value or 'not found'}")
        if not result["available"]:
            print(
                "\nInstall local execution support with: pip install -e '.[pipelines]'",
                file=sys.stderr,
            )
    return 0 if result["available"] else 2


def cmd_import_python(args: argparse.Namespace) -> int:
    try:
        report = discover_python(Path(args.file))
    except (OSError, SyntaxError) as exc:
        print(json.dumps({"code": "SDPS-IMPORT-001", "message": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "declarations": [item.__dict__ for item in report.declarations],
                "unsupported": list(report.unsupported),
                "source_sha256": report.source_sha256,
                "custom_code": [item.__dict__ for item in report.custom_code],
            },
            indent=2,
        )
    )
    return 0


def cmd_import_directory(args: argparse.Namespace) -> int:
    source = args.directory.expanduser().resolve()
    if not source.is_dir():
        print(f"Import directory does not exist: {source}", file=sys.stderr)
        return 2
    try:
        project = _store().create_project(args.name or source.name, example_path=source)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    store = _store()
    reports: list[dict[str, object]] = []
    imported_nodes: list[Node] = []
    imported_edges: list[Edge] = []
    imported_dependencies: list[tuple[str, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        relative = path.relative_to(source).as_posix()
        try:
            if path.suffix == ".py":
                report = discover_python(path)
                declarations = report.declarations
                reports.append(
                    {
                        "file": relative,
                        "kind": "python",
                        "declarations": [item.__dict__ for item in declarations],
                        "unsupported": list(report.unsupported),
                    }
                )
                for declaration in declarations:
                    node_id = f"import-{len(imported_nodes):04d}"
                    imported_nodes.append(
                        Node(
                            id=node_id,
                            type=declaration.kind,
                            config={"name": declaration.name, "source_file": relative},
                        )
                    )
                    imported_dependencies.extend(
                        (node_id, dependency) for dependency in declaration.dependencies
                    )
            elif path.suffix == ".sql":
                sql_report = discover_sql(path)
                sql_declarations = sql_report.declarations
                reports.append(
                    {
                        "file": relative,
                        "kind": "sql",
                        "declarations": [item.__dict__ for item in sql_declarations],
                    }
                )
                for sql_declaration in sql_declarations:
                    node_id = f"import-{len(imported_nodes):04d}"
                    imported_nodes.append(
                        Node(
                            id=node_id,
                            type=sql_declaration.kind,
                            config={"name": sql_declaration.name, "source_file": relative},
                        )
                    )
                    imported_dependencies.extend(
                        (node_id, dependency) for dependency in sql_declaration.dependencies
                    )
        except (OSError, SyntaxError, ValueError):
            continue
    # Directory import produces an openable visual graph by default.  The
    # explicit report-only mode is retained for callers that only want discovery
    # metadata and must not mutate the imported pipeline.
    visualized = not getattr(args, "report_only", False)
    if visualized:
        declaration_names = {str(node.config.get("name")) for node in imported_nodes}
        source_ids: dict[str, str] = {}
        for declaration_id, dependency in sorted(
            imported_dependencies, key=lambda item: (item[1], item[0])
        ):
            if dependency in declaration_names:
                continue
            source_id = source_ids.setdefault(dependency, f"import-source-{len(source_ids):04d}")
            if source_id not in {node.id for node in imported_nodes}:
                imported_nodes.append(
                    Node(
                        id=source_id,
                        type="source.table",
                        config={"table": dependency, "name": dependency},
                    )
                )
            imported_edges.append(
                Edge.model_validate(
                    {
                        "id": f"import-edge-{len(imported_edges):04d}",
                        "from": {"node": source_id, "port": "out"},
                        "to": {"node": declaration_id, "port": "in"},
                    }
                )
            )
        document = PipelineDocument(
            name=project["name"], nodes=imported_nodes, edges=imported_edges
        )
        store.save_pipeline(project["id"], document)
        atomic_write(
            Path(project["path"]) / ".sdpstudio" / "import-report.json",
            json.dumps({"files": reports, "visualized": True}, indent=2, sort_keys=True) + "\n",
        )
    print(
        json.dumps(
            {
                "id": project["id"],
                "name": project["name"],
                "path": project["path"],
                "files": reports,
                "visualized": visualized,
            }
        )
    )
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    store = _store()
    if args.project_command == "list":
        for project in store.list_projects():
            print(f"{project['id']}  {project['name']}  {project['path']}")
        return 0
    if args.project_command == "create":
        example = _example_path(args.from_example) if args.from_example else None
        project = store.create_project(args.name, example_path=example)
        print(project["id"])
        print(project["path"])
        return 0
    if args.project_command == "clone":
        try:
            project = store.clone_project(args.name, args.remote_url, args.branch)
        except (ValueError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(project["id"])
        print(project["path"])
        return 0
    return 2


def cmd_runtime(args: argparse.Namespace) -> int:
    store = _store()
    if args.runtime_command == "list":
        for profile in store.list_runtime_profiles():
            print(f"{profile['id']}  {profile['name']}  {profile['adapter']}")
        return 0
    if args.runtime_command == "add":
        try:
            config = json.loads(args.config or "{}")
            profile = store.create_runtime_profile(args.name, args.adapter, config)
        except (ValueError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(profile["id"])
        return 0
    if args.runtime_command == "probe":
        try:
            result = probe_profile(store.get_runtime_profile(args.profile_id)).model_dump()
        except (KeyError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["available"] else 2
    if args.runtime_command == "delete":
        try:
            store.delete_runtime_profile(args.profile_id)
        except (KeyError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    return 2


def cmd_validate(args: argparse.Namespace) -> int:
    store = _store()
    try:
        document = store.load_pipeline(args.project_id)
    except (KeyError, ValueError) as exc:
        print(f"ERROR SDPS-SCHEMA-001: {exc}")
        return 1
    result = store.generate(args.project_id, write=False)
    problems = validate_graph(document) + result.problems
    for generated in result.files:
        if generated.path.endswith(".py"):
            try:
                ast.parse(generated.content, filename=generated.path)
            except SyntaxError as exc:
                problems.append(
                    Problem(
                        code="SDPS-LINT-001",
                        severity="error",
                        message=f"Generated Python is not syntactically valid: {exc.msg}",
                    )
                )
    if getattr(args, "runtime", None):
        try:
            capabilities = probe_profile(store.get_runtime_profile(args.runtime))
        except (KeyError, ValueError) as exc:
            print(f"ERROR SDPS-RUNTIME-001: {exc}")
            return 1
        if not capabilities.available:
            print(
                "ERROR SDPS-RUNTIME-001: runtime is unavailable"
                f" ({capabilities.details.get('error', 'check runtime prerequisites')})"
            )
            return 1
        problems.extend(validate_capabilities(document, capabilities))
        if capabilities.available:
            temporary_spec = None
            try:
                command, _safe_command, temporary_spec = build_run_command(
                    store.get_runtime_profile(args.runtime),
                    project=store.project_path(args.project_id),
                    run_id="cli-validate",
                    mode="incremental",
                    selected=[],
                )
                command[1] = "dry-run"
                completed = subprocess.run(
                    command,
                    cwd=store.project_path(args.project_id),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    shell=False,
                )
                if completed.returncode != 0:
                    problems.append(
                        Problem(
                            code="SDPS-VALIDATE-DRY-RUN-001",
                            severity="error",
                            message=(completed.stderr or completed.stdout).strip()
                            or "Spark pipelines dry-run failed",
                            remediation="Inspect the Spark dry-run output and runtime profile.",
                        )
                    )
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                problems.append(
                    Problem(
                        code="SDPS-VALIDATE-DRY-RUN-002",
                        severity="error",
                        message=f"Unable to execute Spark pipelines dry-run: {exc}",
                        remediation="Verify the selected runtime and spark-pipelines executable.",
                    )
                )
            finally:
                if temporary_spec is not None:
                    temporary_spec.unlink(missing_ok=True)
    seen = set()
    errors = 0
    for p in problems:
        key = (p.code, p.node_id, p.message)
        if key in seen:
            continue
        seen.add(key)
        print(
            f"{p.severity.upper():7} {p.code}: {p.message}"
            + (f" [{p.node_id}]" if p.node_id else "")
        )
        errors += p.severity == "error"
    if not seen:
        print("Pipeline model is valid.")
    return 1 if errors else 0


def cmd_generate(args: argparse.Namespace) -> int:
    store = _store()
    if args.target == "sql":
        result = store.generate_sql(args.project_id, write=not args.check)
    else:
        result = store.generate(args.project_id, write=not args.check)
    if any(p.severity == "error" for p in result.problems):
        for p in result.problems:
            print(f"{p.severity.upper()} {p.code}: {p.message}", file=sys.stderr)
        return 1
    if args.check:
        project_path = store.project_path(args.project_id)
        drift = False
        for file in result.files:
            target = project_path / file.path
            current_hash = (
                hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            )
            if current_hash != file.sha256:
                print(f"drift: {file.path}")
                drift = True
        if args.target == "sql":
            source_map = project_path / ".sdpstudio" / "source-maps" / "generated.sql.map.json"
        else:
            source_map = project_path / ".sdpstudio" / "source-maps" / "generated.py.map.json"
        if not source_map.exists():
            print(f"drift: {source_map.relative_to(project_path)}")
            drift = True
        else:
            expected_map = {
                "schemaVersion": 1,
                "mappings": [mapping.model_dump() for mapping in result.source_map],
                "files": {generated.path: generated.sha256 for generated in result.files},
            }
            try:
                if (
                    source_map.read_text(encoding="utf-8")
                    != json.dumps(expected_map, indent=2) + "\n"
                ):
                    print(f"drift: {source_map.relative_to(project_path)}")
                    drift = True
            except OSError:
                print(f"drift: {source_map.relative_to(project_path)}")
                drift = True
        return 1 if drift else 0
    for f in result.files:
        print(f.content if args.stdout else f"generated {f.path} {f.sha256[:12]}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    store = _store()
    try:
        if args.history_command == "list":
            print(json.dumps(store.list_history(args.project_id), indent=2, default=str))
            return 0
        if args.history_command == "restore":
            document = store.restore_history(args.project_id, args.snapshot_id)
            print(json.dumps(document.model_dump(by_alias=True), indent=2, default=str))
            return 0
    except (KeyError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


def cmd_debug_bundle(args: argparse.Namespace) -> int:
    store = _store()
    try:
        run = store.get_run(args.run_id)
        project = store.project_path(run["project_id"])
        artifact_dir = project / ".sdpstudio" / "runtime" / "run-artifacts" / args.run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        registered = {}
        for item in store.list_secrets():
            try:
                registered[item["name"]] = store.resolve_secret(item["name"])
            except (KeyError, ValueError):
                continue
        entries = build_entries(
            run,
            store.run_events(args.run_id),
            store.get_node_snapshots(args.run_id),
            artifact_dir=artifact_dir,
            project=project,
            redact_value=_redact_bundle_value,
            registered_secrets=registered,
            redact_registered=_redact_registered_secrets,
        )
        manifest = {
            "schema": 1,
            "files": [
                {"path": name, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
                for name, content in sorted(entries.items())
            ],
        }
        entries["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        output = args.output or Path.cwd() / f"sdpstudio-debug-{args.run_id}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(entries.items()):
                archive.writestr(name, content)
        print(str(output.resolve()))
        return 0
    except (KeyError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


async def _run_project(args: argparse.Namespace) -> int:
    store = _store()
    result = store.generate(args.project_id, write=True)
    if any(p.severity == "error" for p in result.problems):
        for p in result.problems:
            print(f"{p.severity.upper()} {p.code}: {p.message}", file=sys.stderr)
        return 1
    mode = "incremental"
    selected: list[str] = []
    if args.full_refresh_all:
        mode = "full-refresh-all"
    elif args.full_refresh:
        mode, selected = "full-refresh", args.full_refresh
    elif args.refresh:
        mode, selected = "refresh", args.refresh
    runtime = LocalRuntime(store)
    profile = store.get_runtime_profile(args.runtime) if args.runtime else None
    record = runtime.submit(args.project_id, mode, selected, profile=profile)
    print(f"run {record.id}")
    task = runtime.tasks.get(record.id)
    if task:
        await task
    final = store.get_run(record.id)
    for event in store.run_events(record.id):
        if event["kind"] in {"log", "problem"}:
            print(event["message"])
    print(f"status: {final['status']}")
    return 0 if final["status"] == "succeeded" else 1


async def _preview_node(args: argparse.Namespace) -> int:
    store = _store()
    runtime = LocalRuntime(store)
    try:
        profile = store.get_runtime_profile(args.runtime) if args.runtime else None
        result = await runtime.preview(args.project_id, args.node_id, args.limit, profile=profile)
    except (KeyError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    fields = result.get("schema", [])
    rows = result.get("rows", [])
    if fields:
        print("schema:")
        for field in fields:
            if isinstance(field, dict):
                print(
                    f"  {field.get('name', '?')}: {field.get('type', '?')}"
                    + (" nullable" if field.get("nullable") else "")
                )
            else:
                print(f"  {field}")
    print(f"rows: {len(rows)}")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, default=str))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    if args.open:
        import threading
        import time

        def opener() -> None:
            time.sleep(0.7)
            webbrowser.open(f"http://127.0.0.1:{args.port}")

        threading.Thread(target=opener, daemon=True).start()
    try:
        app = create_app(bind_host=args.host, allow_insecure_remote=args.insecure_allow_remote)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


async def _run_worker(args: argparse.Namespace) -> int:
    """Run the database-backed scheduler without starting another HTTP server."""
    store = _store()
    if args.runs_only:
        run_worker = DurableRunWorker(
            store,
            args.worker_id,
            lambda record: execute_queued_local_run(store, record),
        )
        try:
            while True:
                claimed = await run_worker.poll_once_async(lease_seconds=args.lease_seconds)
                if claimed is None:
                    await asyncio.sleep(args.interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            return 0
    runtime = LocalRuntime(store)

    async def dispatch(schedule: dict[str, object]) -> None:
        profile = (
            store.get_runtime_profile(str(schedule["runtime_profile_id"]))
            if schedule.get("runtime_profile_id")
            else None
        )
        runtime.submit(
            str(schedule["project_id"]),
            str(schedule.get("mode", "incremental")),
            [],
            profile=profile,
        )

    worker = ScheduleWorker(
        lambda: [
            schedule
            for project in store.list_projects()
            for schedule in store.list_schedules(project["id"])
        ],
        dispatch,
        interval_seconds=args.interval,
        claim=store.claim_schedule,
    )
    await worker.start()
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    finally:
        await worker.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdpstudio", description="SDP Studio — visual pipelines for Apache Spark"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="start the SDP Studio local server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--open", action="store_true")
    serve.add_argument("--insecure-allow-remote", action="store_true")
    serve.set_defaults(func=cmd_serve)

    init = sub.add_parser("init", help="initialize a project in a directory")
    init.add_argument("directory", type=Path)
    init.add_argument("--name")
    init.set_defaults(func=cmd_init)

    version = sub.add_parser("version", help="print the installed SDP Studio version")
    version.set_defaults(func=cmd_version)

    worker = sub.add_parser("worker", help="run the shared scheduler worker")
    worker.add_argument("--interval", type=float, default=30.0)
    worker.add_argument("--runs-only", action="store_true", help="consume durable queued runs")
    worker.add_argument("--worker-id", default="sdpstudio-worker")
    worker.add_argument("--lease-seconds", type=int, default=60)
    worker.set_defaults(async_func=_run_worker)

    doctor = sub.add_parser("doctor", help="probe local Spark SDP capabilities")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    import_python = sub.add_parser(
        "import-python", help="discover SDP declarations without executing Python"
    )
    import_python.add_argument("file", type=Path)
    import_python.set_defaults(func=cmd_import_python)

    import_directory = sub.add_parser(
        "import", help="import a project directory without modifying the source"
    )
    import_directory.add_argument("directory", type=Path)
    import_directory.add_argument("--name")
    import_directory.add_argument("--visualize", action="store_true")
    import_directory.add_argument(
        "--report-only",
        action="store_true",
        help="discover files without persisting a visual graph",
    )
    import_directory.set_defaults(func=cmd_import_directory)

    project = sub.add_parser("project", help="manage projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    list_p = project_sub.add_parser("list")
    list_p.set_defaults(func=cmd_project)
    create = project_sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("--from-example", choices=["retail-etl"])
    create.set_defaults(func=cmd_project)
    clone_project = project_sub.add_parser("clone")
    clone_project.add_argument("name")
    clone_project.add_argument("remote_url")
    clone_project.add_argument("--branch")
    clone_project.set_defaults(func=cmd_project)

    runtime = sub.add_parser("runtime", help="manage execution runtime profiles")
    runtime_sub = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_list = runtime_sub.add_parser("list")
    runtime_list.set_defaults(func=cmd_runtime)
    runtime_add = runtime_sub.add_parser("add")
    runtime_add.add_argument("name")
    runtime_add.add_argument(
        "adapter", help="built-in adapter name or an installed runtime plugin identifier"
    )
    runtime_add.add_argument(
        "--config", default="{}", help="JSON configuration; use *_env references for secrets"
    )
    runtime_add.set_defaults(func=cmd_runtime)
    runtime_probe = runtime_sub.add_parser("probe")
    runtime_probe.add_argument("profile_id")
    runtime_probe.set_defaults(func=cmd_runtime)
    runtime_delete = runtime_sub.add_parser("delete")
    runtime_delete.add_argument("profile_id")
    runtime_delete.set_defaults(func=cmd_runtime)

    validate = sub.add_parser("validate")
    validate.add_argument("project_id")
    validate.add_argument("--runtime", help="runtime profile id to probe before validation")
    validate.set_defaults(func=cmd_validate)

    generate = sub.add_parser("generate")
    generate.add_argument("project_id")
    generate.add_argument("--check", action="store_true")
    generate.add_argument("--target", choices=["python", "sql"], default="python")
    generate.add_argument(
        "--stdout", action="store_true", help="print generated source (SQL target)"
    )
    generate.set_defaults(func=cmd_generate)

    history = sub.add_parser("history", help="inspect and restore local project history")
    history_sub = history.add_subparsers(dest="history_command", required=True)
    history_list = history_sub.add_parser("list")
    history_list.add_argument("project_id")
    history_list.set_defaults(func=cmd_history)
    history_restore = history_sub.add_parser("restore")
    history_restore.add_argument("project_id")
    history_restore.add_argument("snapshot_id")
    history_restore.set_defaults(func=cmd_history)

    debug = sub.add_parser("debug", help="export debugging artifacts")
    debug_sub = debug.add_subparsers(dest="debug_command", required=True)
    bundle = debug_sub.add_parser("bundle")
    bundle.add_argument("run_id")
    bundle.add_argument("--output", type=Path)
    bundle.set_defaults(func=cmd_debug_bundle)

    preview = sub.add_parser(
        "preview", help="preview a visual node using the selected Spark runtime"
    )
    preview.add_argument("project_id")
    preview.add_argument("node_id")
    preview.add_argument("--runtime", help="runtime profile id (defaults to local)")
    preview.add_argument("--limit", type=int, default=50, choices=range(1, 201), metavar="1..200")
    preview.add_argument("--json", action="store_true")
    preview.set_defaults(async_func=_preview_node)

    run = sub.add_parser("run")
    run.add_argument("project_id")
    run.add_argument("--refresh", action="append")
    run.add_argument("--full-refresh", action="append")
    run.add_argument("--full-refresh-all", action="store_true")
    run.add_argument("--runtime", help="runtime profile id (defaults to local)")
    run.set_defaults(async_func=_run_project)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = asyncio.run(args.async_func(args)) if hasattr(args, "async_func") else args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
