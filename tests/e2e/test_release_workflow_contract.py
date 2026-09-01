"""Browser-independent acceptance contract used when Playwright is unavailable."""

from pathlib import Path


def test_built_react_artifact_is_served() -> None:
    static_root = Path(__file__).parents[2] / "python" / "sdpstudio_server" / "static" / "react"
    assert (static_root / "react-index.html").is_file()
    assert any(static_root.glob("assets/react-index-*.js"))
