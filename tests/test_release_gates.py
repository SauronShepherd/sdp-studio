import json
from pathlib import Path

from scripts.license_gate import check_sbom
from scripts.openapi_client import generate, render_client
from scripts.sbom import _license_from_python_metadata, build_sbom


def test_sbom_is_deterministic_and_cyclonedx_shaped(tmp_path: Path):
    root = tmp_path
    (root / "pnpm-lock.yaml").write_text("packages:\n    react@19.0.0:\n", encoding="utf-8")
    first = build_sbom(root)
    second = build_sbom(root)
    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert any(item["purl"] == "pkg:npm/react@19.0.0" for item in first["components"])


def test_sbom_prefers_spdx_python_license_metadata():
    class Metadata(dict):
        def get_all(self, _name):
            return []

    class Distribution:
        metadata = Metadata(
            {
                "License-Expression": "Apache-2.0 OR BSD-3-Clause",
                "License": "UNKNOWN",
            }
        )

    assert _license_from_python_metadata(Distribution()) == "Apache-2.0 OR BSD-3-Clause"


def test_sbom_uses_installed_npm_manifest_license_metadata(tmp_path: Path):
    (tmp_path / "pnpm-lock.yaml").write_text("packages:\n    react@19.0.0:\n", encoding="utf-8")
    manifest = (
        tmp_path
        / "web"
        / "node_modules"
        / ".pnpm"
        / "react@19.0.0"
        / "node_modules"
        / "react"
        / "package.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": "react", "version": "19.0.0", "license": "MIT"}), encoding="utf-8"
    )
    components = build_sbom(tmp_path)["components"]
    react = next(item for item in components if item["purl"] == "pkg:npm/react@19.0.0")
    assert react["licenses"][0]["license"]["name"] == "MIT"


def test_sbom_resolves_scoped_licenses_from_workspace_pnpm_store(tmp_path: Path):
    (tmp_path / "pnpm-lock.yaml").write_text(
        "packages:\n    '@scope/tool@1.2.3':\n", encoding="utf-8"
    )
    manifest = (
        tmp_path
        / "node_modules"
        / ".pnpm"
        / "@scope+tool@1.2.3"
        / "node_modules"
        / "@scope"
        / "tool"
        / "package.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": "@scope/tool", "version": "1.2.3", "license": "Apache-2.0"}),
        encoding="utf-8",
    )
    components = build_sbom(tmp_path)["components"]
    scoped = next(item for item in components if item["purl"] == "pkg:npm/@scope/tool@1.2.3")
    assert scoped["licenses"][0]["license"]["name"] == "Apache-2.0"


def test_license_gate_rejects_denylisted_license(tmp_path: Path):
    path = tmp_path / "sbom.json"
    path.write_text(
        json.dumps(
            {"components": [{"name": "bad", "licenses": [{"license": {"name": "GPL-3.0"}}]}]}
        ),
        encoding="utf-8",
    )
    assert check_sbom(path) == ["bad: denied license GPL-3.0"]


def test_license_gate_allows_explicitly_approved_optional_postgres_adapter(tmp_path: Path):
    path = tmp_path / "sbom.json"
    path.write_text(
        json.dumps(
            {
                "components": [
                    {"name": "psycopg", "licenses": [{"license": {"name": "LGPL-3.0-only"}}]}
                ]
            }
        ),
        encoding="utf-8",
    )
    assert check_sbom(path) == []


def test_openapi_client_generation_is_deterministic_and_checks_drift(tmp_path: Path):
    document = {
        "paths": {"/api/runs": {"get": {}, "post": {}}, "/api/projects": {}},
        "components": {
            "schemas": {
                "Pipeline": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                }
            }
        },
    }
    output = tmp_path / "openapi.generated.ts"
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")
    assert generate(tmp_path / "openapi.json", output)
    assert generate(tmp_path / "openapi.json", output, check=True)
    assert render_client(document).count("/api/") == 4
    assert '{ path: "/api/runs", method: "get" }' in render_client(document)
    assert "export interface Pipeline" in render_client(document)
    output.write_text(output.read_text(encoding="utf-8") + "// drift\n", encoding="utf-8")
    assert not generate(tmp_path / "openapi.json", output, check=True)


def test_deployment_manifests_expose_required_team_services():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = Path("deploy/docker/Dockerfile").read_text(encoding="utf-8")
    helm = Path("deploy/helm/sdpstudio/templates/deployment.yaml").read_text(encoding="utf-8")
    assert "server:" in compose and "worker:" in compose and "postgres:" in compose
    assert 'command: ["worker", "--runs-only"]' in compose
    assert "SDPSTUDIO_DATABASE_URL" in compose
    assert "SDPSTUDIO_AUTH_TOKEN" in compose
    assert "condition: service_healthy" in compose
    assert "HEALTHCHECK" in dockerfile and "USER sdpstudio" in dockerfile
    assert "runAsNonRoot: true" in helm


def test_react_build_is_the_canonical_server_entrypoint():
    vite = Path("web/vite.config.ts").read_text(encoding="utf-8")
    app = Path("python/sdpstudio_server/app.py").read_text(encoding="utf-8")
    assert 'command === "build" ? "/static/react/" : "/"' in vite
    assert 'react_root / "react-index.html"' in app


def test_spec_endpoint_groups_are_present_in_openapi(tmp_path: Path):
    from sdpstudio_server.app import create_app

    paths = set(create_app(tmp_path).openapi()["paths"])
    required = {
        "/api/projects/{project_id}/pipelines",
        "/api/runtime-profiles/{profile_id}",
        "/api/runtime-profiles/{profile_id}/test",
        "/api/projects/{project_id}/schedules/{schedule_id}/run-now",
        "/api/projects/{project_id}/git/stage",
        "/api/projects/{project_id}/git/unstage",
        "/api/projects/{project_id}/git/conflicts",
        "/api/projects/{project_id}/git/reviews",
        "/api/debug/streaming/analyze",
        "/api/debug/redaction-preview",
        "/api/projects/{project_id}",
        "/api/projects/{project_id}/history/{snapshot_id}",
        "/api/projects/{project_id}/import",
        "/api/projects/{project_id}/validate-model",
        "/api/runs/{run_id}/events",
        "/api/runs/{run_id}/nodes/{node_id}",
        "/api/runs/compare",
        "/api/runs/{run_id}/debug-bundle",
        "/api/secrets",
        "/api/schedules",
    }
    assert required <= paths


def test_ci_package_gate_publishes_checksum_manifest():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/release_manifest.py" in workflow
    assert "dist/release-manifest.json" in workflow


def test_readme_documents_the_spec_reference_quickstart():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert 'pip install "pyspark[pipelines]==4.2.0" sdpstudio' in readme
    assert "sdpstudio doctor" in readme
    assert "sdpstudio serve --open" in readme
