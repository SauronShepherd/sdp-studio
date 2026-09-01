from __future__ import annotations

import subprocess

import pytest

from scripts import environment_gate


def test_databricks_gate_requires_real_auth_and_workspace_probe(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL", "https://workspace.example")
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "sda")
    monkeypatch.setattr(environment_gate.shutil, "which", lambda name: "databricks.exe")
    calls: list[list[str]] = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["auth", "describe"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="Host: https://workspace.example\n", stderr=""
            )
        return subprocess.CompletedProcess(command, 0, stdout="ID  Name  State\n", stderr="")

    monkeypatch.setattr(environment_gate.subprocess, "run", run)
    assert environment_gate.main(["databricks"]) == 0
    assert calls == [
        ["databricks.exe", "auth", "describe", "--profile", "sda"],
        ["databricks.exe", "clusters", "list", "--profile", "sda"],
    ]


def test_databricks_gate_rejects_profile_host_mismatch(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL", "https://expected.example")
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "sda")
    monkeypatch.setattr(environment_gate.shutil, "which", lambda name: "databricks.exe")
    monkeypatch.setattr(
        environment_gate.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="Host: https://other.example\n", stderr=""
        ),
    )
    with pytest.raises(SystemExit, match="does not match"):
        environment_gate.main(["databricks"])


def test_spark_gate_resolves_windows_script_from_selected_interpreter(tmp_path, monkeypatch):
    spark_python = tmp_path / "Python312" / "python.exe"
    spark_python.parent.joinpath("Scripts").mkdir(parents=True)
    spark_python.parent.joinpath("Scripts", "spark-pipelines").write_text("", encoding="utf-8")
    monkeypatch.setenv("SDPSTUDIO_RELEASE_SPARK_CONNECT_REMOTE", "remote")
    monkeypatch.setenv("SDPSTUDIO_SPARK_PYTHON", str(spark_python))
    monkeypatch.setattr(
        environment_gate.shutil,
        "which",
        lambda name: "java.exe" if name == "java" else None,
    )

    def run(command, **kwargs):
        if command[1:] == [
            "-c",
            "import pyspark; from pyspark import pipelines; print(pyspark.__version__)",
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="4.2.0\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr='version "21.0.1"')

    monkeypatch.setattr(environment_gate.subprocess, "run", run)
    assert environment_gate.main(["spark-connect"]) == 0
