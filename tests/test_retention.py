from datetime import UTC, datetime, timedelta

from sdpstudio_server.retention import RetentionPolicy, cleanup_runtime_artifacts


def test_runtime_retention_removes_old_and_excess_artifacts(tmp_path):
    runtime = tmp_path / ".sdpstudio" / "runtime" / "previews"
    runtime.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (runtime / name).mkdir()
    old = datetime.now(UTC) - timedelta(days=10)
    for item in runtime.iterdir():
        item.touch()
        item.chmod(0o600)
        import os

        os.utime(item, (old.timestamp(), old.timestamp()))
    result = cleanup_runtime_artifacts(
        tmp_path, RetentionPolicy(max_count=1, max_age_days=5), now=datetime.now(UTC)
    )
    assert len(result["removed"]) == 3
    assert not list(runtime.iterdir())


def test_retention_policy_rejects_invalid_limits(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_ARTIFACT_MAX_COUNT", "0")
    try:
        RetentionPolicy.from_env()
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("invalid retention limit accepted")
