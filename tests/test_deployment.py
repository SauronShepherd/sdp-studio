from pathlib import Path


def test_container_and_helm_deployment_are_non_root_and_probed():
    root = Path(__file__).parents[1]
    dockerfile = (root / "deploy/docker/Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    deployment = (root / "deploy/helm/sdpstudio/templates/deployment.yaml").read_text(
        encoding="utf-8"
    )
    chart = root / "deploy/helm/sdpstudio/templates"
    assert "USER sdpstudio" in dockerfile
    assert 'pip install --no-cache-dir ".[postgres]"' in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "AS server" in dockerfile and "AS worker" in dockerfile and "AS runner" in dockerfile
    assert "target: server" in compose and "target: worker" in compose
    assert "runAsNonRoot: true" in deployment
    assert "readinessProbe:" in deployment
    assert "livenessProbe:" in deployment
    assert (chart / "worker-deployment.yaml").exists()
    assert (chart / "configmap.yaml").exists()
    assert (chart / "pvc.yaml").exists()
    assert "persistentVolumeClaim:" in deployment
    assert all(f"  {service}:" in compose for service in ("server", "worker", "postgres"))
    assert "condition: service_healthy" in compose
    worker = (chart / "worker-deployment.yaml").read_text(encoding="utf-8")
    assert 'command: ["worker", "--runs-only"]' in worker


def test_helm_ingress_is_optional_and_routes_to_service():
    root = Path(__file__).parents[1]
    values = (root / "deploy/helm/sdpstudio/values.yaml").read_text(encoding="utf-8")
    ingress = (root / "deploy/helm/sdpstudio/templates/ingress.yaml").read_text(encoding="utf-8")
    assert "enabled: false" in values
    assert "kind: Ingress" in ingress
    assert "service:" in ingress
    assert "number: {{ $.Values.service.port }}" in ingress
