from __future__ import annotations

import json
import sys

from sdpstudio_server.storage import DataStore


def main() -> None:
    """Dispatch security maintenance commands before the legacy CLI parser."""

    if sys.argv[1:3] == ["secrets", "migrate"]:
        if len(sys.argv) != 3:
            print("usage: sdpstudio secrets migrate", file=sys.stderr)
            raise SystemExit(2)
        result = DataStore().rotate_secrets()
        print(json.dumps({"status": "migrated", **result}, sort_keys=True))
        return

    from .main import main as application_main

    application_main()


if __name__ == "__main__":
    main()
