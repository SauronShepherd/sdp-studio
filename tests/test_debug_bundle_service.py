from pathlib import Path

from sdpstudio_server.debug_bundle_service import build_entries


def test_debug_bundle_service_builds_fingerprints_and_redacts_registered_secrets(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "plan.json").write_text('{"token":"secret-value"}\n', encoding="utf-8")

    entries = build_entries(
        {"id": "run-1", "token": "secret-value"},
        [],
        [{"node_id": "n1", "schema": [{"name": "id", "type": "long"}]}],
        artifact_dir=artifact_dir,
        project=tmp_path,
        redact_value=lambda value: value,
        registered_secrets={"token": "secret-value"},
        redact_registered=lambda text, secrets: (
            text.replace("secret-value", "[REDACTED]"),
            {"token"},
        ),
    )
    assert b"secret-value" not in entries["plan.json"]
    assert b"n1" in entries["schema-fingerprints.json"]
