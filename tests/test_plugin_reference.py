import json
from pathlib import Path

from scripts.plugin_reference import build_reference


def test_plugin_reference_matches_source_contract():
    path = Path("docs/reference/plugin-sdk.json")
    assert json.loads(path.read_text(encoding="utf-8")) == build_reference()
