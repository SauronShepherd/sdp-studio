from pathlib import Path

from scripts.qualify import qualify


def test_qualification_report_has_explicit_gate_names(tmp_path: Path, monkeypatch):
    commands = []

    def fake_gate(root, name, command):
        commands.append((name, command))
        return {"name": name, "command": command, "passed": True, "returncode": 0}

    monkeypatch.setattr("scripts.qualify.run_gate", fake_gate)
    report = qualify(tmp_path, browser=True, spark=True)
    assert report["passed"] is True
    assert {name for name, _ in commands} >= {
        "python-tests",
        "web-build",
        "browser-e2e",
        "spark-smoke",
        "spark-row-trace",
        "contract-tests",
        "python-typecheck",
        "codegen-goldens",
        "cli-contract",
        "roundtrip-contract",
        "kubernetes-contract",
        "security-contract",
        "databricks-adapter-contract",
        "scheduler-contract",
        "collaboration-contract",
        "git-contract",
    }


def test_kubernetes_qualification_is_opt_in(tmp_path: Path, monkeypatch):
    commands = []
    monkeypatch.setattr(
        "scripts.qualify.run_gate",
        lambda root, name, command: commands.append(name) or {"name": name, "passed": True},
    )
    report = qualify(tmp_path, kubernetes=True)
    assert report["passed"] is True
    assert "kubernetes-kind-contract" in commands


def test_release_qualification_is_fail_closed_and_includes_environment_gates(
    tmp_path: Path, monkeypatch
):
    commands = []
    monkeypatch.setattr(
        "scripts.qualify.run_gate",
        lambda root, name, command: commands.append(name) or {"name": name, "passed": True},
    )
    report = qualify(tmp_path, release=True)
    assert report["passed"] is True
    assert {"browser-e2e", "spark-smoke", "kubernetes-kind-contract", "container-smoke"} <= set(
        commands
    )


def test_gate_evidence_contains_duration(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr("scripts.qualify.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "scripts.qualify.subprocess.run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""}
        )(),
    )
    from scripts.qualify import run_gate

    result = run_gate(tmp_path, "evidence", ["python", "-V"])
    assert result["passed"] is True
    assert result["duration_seconds"] >= 0
    assert '"event": "gate_started"' in capsys.readouterr().out


def test_spark_qualification_can_select_a_spark_compatible_python(tmp_path: Path, monkeypatch):
    commands = []
    monkeypatch.setenv("SDPSTUDIO_SPARK_PYTHON", "python312")
    monkeypatch.setattr(
        "scripts.qualify.run_gate",
        lambda root, name, command: (
            commands.append((name, command)) or {"name": name, "passed": True}
        ),
    )
    qualify(tmp_path, spark=True)
    spark_commands = [command for name, command in commands if name.startswith("spark-")]
    assert spark_commands
    assert all(command[0] == "python312" for command in spark_commands)
