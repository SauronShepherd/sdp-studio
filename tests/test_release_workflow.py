from pathlib import Path


def test_release_workflow_invokes_fail_closed_matrix_and_uploads_evidence():
    workflow = Path(".github/workflows/release-qualification.yml").read_text(encoding="utf-8")
    assert (
        "python scripts/qualify.py --release --output dist/qualification-release.json" in workflow
    )
    assert "SDPSTUDIO_RELEASE_SPARK_CONNECT_REMOTE" in workflow
    assert "SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL" in workflow
    assert "sdpstudio-release-qualification" in workflow
