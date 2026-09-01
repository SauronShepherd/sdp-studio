from pathlib import Path

from scripts.package_smoke import run


def test_package_smoke_script_is_callable(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("scripts.package_smoke.subprocess.run", fake_run)
    monkeypatch.setattr(
        "scripts.package_smoke.tempfile.TemporaryDirectory", lambda **_: _TempDir(tmp_path)
    )
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "sdpstudio-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "dist" / "sdpstudio-0.1.0.tar.gz").write_bytes(b"source")
    run(tmp_path)
    assert any("-m" in command and "build" in command for command in calls)


class _TempDir:
    def __init__(self, root: Path):
        self.root = root

    def __enter__(self):
        return str(self.root)

    def __exit__(self, *_):
        return False
