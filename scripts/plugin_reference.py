"""Generate the versioned, typed plugin contract reference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from sdpstudio_core.plugin_contract import SDK_VERSION  # noqa: E402
from sdpstudio_core.plugins import PLUGIN_GROUPS  # noqa: E402


def build_reference() -> dict[str, object]:
    return {
        "schema": 1,
        "sdk_version": SDK_VERSION,
        "api_version": "v1",
        "manifest": {
            "api_version": "string (required; v1)",
            "license": "string (required)",
            "plugin_version": "semver (required)",
            "capabilities": "array[string] (required)",
            "min_sdpstudio_version": "semver (optional; defaults to 0.0.0)",
        },
        "entry_point_groups": dict(sorted(PLUGIN_GROUPS.items())),
        "compatibility": "Plugins requiring a newer SDK or unknown API version are disabled at startup.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/reference/plugin-sdk.json"))
    args = parser.parse_args()
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_reference(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
