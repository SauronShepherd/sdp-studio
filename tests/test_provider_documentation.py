from pathlib import Path


def test_provider_guidance_points_to_vault():
    root = Path(__file__).parents[1]
    assert "provider.github.token" in (root / "docs/reference/README.md").read_text(
        encoding="utf-8"
    )
    assert "provider.github.token" in (root / "python/sdpstudio_server/static/app.js").read_text(
        encoding="utf-8"
    )
