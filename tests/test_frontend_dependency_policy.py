from __future__ import annotations

import json
from pathlib import Path


def test_dompurify_security_override_is_locked_to_patched_release() -> None:
    root = Path(__file__).resolve().parents[1]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    override = package["pnpm"]["overrides"]["dompurify"]

    assert override == "3.4.14"

    lockfile = (root / "pnpm-lock.yaml").read_text(encoding="utf-8")
    assert "dompurify: 3.4.14" in lockfile
    assert "dompurify@3.4.14:" in lockfile
    assert "dompurify@3.4.8:" not in lockfile
