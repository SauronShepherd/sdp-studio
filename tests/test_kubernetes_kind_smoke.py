from __future__ import annotations

import subprocess

from scripts import kubernetes_kind_smoke


def test_kind_smoke_uses_safe_kubectl_lifecycle(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-2:] == ["-o", "json"]:
            return subprocess.CompletedProcess(
                command, 0, stdout='{"status":{"phase":"Succeeded"}}', stderr=""
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(kubernetes_kind_smoke.subprocess, "run", fake_run)
    result = kubernetes_kind_smoke.smoke("ns", "pod", timeout_seconds=1)
    assert result["phase"] == "Succeeded"
    assert all("shell" not in call for call in calls)
    assert any(command[0:3] == ["kubectl", "-n", "ns"] for command in calls)
