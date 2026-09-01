"""Run a bounded live pod lifecycle smoke against a kind cluster."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True, timeout=30)


def smoke(namespace: str, pod: str, timeout_seconds: int = 90) -> dict[str, object]:
    run(["kubectl", "create", "namespace", namespace], check=False)
    run(
        [
            "kubectl",
            "-n",
            namespace,
            "run",
            pod,
            "--image=busybox:1.36",
            "--restart=Never",
            "--command",
            "--",
            "sh",
            "-c",
            "echo sdpstudio-kind-smoke",
        ]
    )
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            result = run(["kubectl", "-n", namespace, "get", "pod", pod, "-o", "json"], check=False)
            if result.returncode == 0:
                payload = json.loads(result.stdout)
                phase = str((payload.get("status") or {}).get("phase", ""))
                if phase in {"Succeeded", "Failed"}:
                    if phase != "Succeeded":
                        raise RuntimeError(f"Kubernetes smoke pod failed: {phase}")
                    return {"namespace": namespace, "pod": pod, "phase": phase}
            time.sleep(1)
        raise TimeoutError("Kubernetes smoke pod did not reach a terminal state")
    finally:
        run(
            ["kubectl", "-n", namespace, "delete", "pod", pod, "--ignore-not-found=true"],
            check=False,
        )
        run(["kubectl", "delete", "namespace", namespace, "--ignore-not-found=true"], check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="sdpstudio-qualification")
    parser.add_argument("--pod", default="sdpstudio-kind-smoke")
    args = parser.parse_args()
    print(json.dumps(smoke(args.namespace, args.pod), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
