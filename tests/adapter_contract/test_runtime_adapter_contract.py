"""Shared adapter contract smoke tests kept beside the adapter suite."""

from pathlib import Path

from sdpstudio_runners.adapters import DurableLocalRuntimeAdapter


def test_local_adapter_exposes_all_runtime_contract_operations(tmp_path: Path) -> None:
    adapter = DurableLocalRuntimeAdapter(None)
    for name in (
        "probe",
        "validate",
        "preview",
        "submit",
        "cancel",
        "status",
        "stream_events",
        "collect_artifacts",
    ):
        assert callable(getattr(adapter, name))
