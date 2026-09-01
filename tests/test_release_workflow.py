from pathlib import Path


def test_release_workflow_invokes_fail_closed_matrix_and_uploads_evidence():
    workflow = Path(".github/workflows/release-qualification.yml").read_text(encoding="utf-8")
    assert "workflow_call:" in workflow
    assert (
        "python scripts/qualify.py --release --output dist/qualification-release.json" in workflow
    )
    assert "SDPSTUDIO_RELEASE_SPARK_CONNECT_REMOTE" in workflow
    assert "SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL" in workflow
    assert "sdpstudio-release-qualification" in workflow


def test_publish_workflow_is_qualification_gated_signed_and_oidc_published():
    workflow = Path(".github/workflows/publish-release.yml").read_text(encoding="utf-8")
    assert "uses: ./.github/workflows/release-qualification.yml" in workflow
    assert "needs: qualify" in workflow
    assert "actions/attest-build-provenance@v4" in workflow
    assert "sigstore/gh-action-sigstore-python@v3.4.0" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "id-token: write" in workflow
    assert "target: [server, worker, runner]" in workflow
    assert "docker/build-push-action@v6" in workflow
    assert "provenance: mode=max" in workflow
    assert "sbom: true" in workflow
