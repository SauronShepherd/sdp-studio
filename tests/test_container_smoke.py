from pathlib import Path

from scripts.container_smoke import run


def test_container_smoke_supplies_non_secret_compose_values(tmp_path: Path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr("scripts.container_smoke.subprocess.run", fake_run)
    run(tmp_path)
    assert calls[0][0] == ["docker", "compose", "config", "--quiet"]
    assert calls[0][1]["env"]["POSTGRES_PASSWORD"] == "qualification-only"
