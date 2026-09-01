import json
from pathlib import Path

from scripts.release_manifest import build_manifest


def test_release_manifest_is_deterministic_and_hashed(tmp_path: Path):
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    manifest = build_manifest(tmp_path, [second, first])
    assert [item["path"] for item in manifest["artifacts"]] == ["a.txt", "b.txt"]
    assert len(manifest["artifacts"][0]["sha256"]) == 64
    assert json.dumps(manifest, sort_keys=True) == json.dumps(
        build_manifest(tmp_path, [first, second]), sort_keys=True
    )
