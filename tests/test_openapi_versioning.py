from sdpstudio_server.app import create_app


def test_openapi_describes_versioned_api_aliases(tmp_path):
    paths = create_app(tmp_path).openapi()["paths"]
    assert "/api/projects" in paths
    assert "/api/v1/projects" in paths
    assert "/api/v1/projects/{project_id}/git/log" in paths
