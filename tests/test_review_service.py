import pytest
from sdpstudio_server import review_service


def test_create_review_dispatches_provider_and_normalizes_result(monkeypatch):
    monkeypatch.setattr(
        review_service,
        "create_github_pull_request",
        lambda *args, **kwargs: {"html_url": "https://github.test/pr/1", "number": 1},
    )
    result = review_service.create_review(
        "https://github.com/acme/demo.git",
        provider="auto",
        title="Update",
        body="Body",
        head="feature",
        base="main",
    )
    assert result["provider"] == "github"
    assert result["number"] == 1


def test_create_review_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="not recognized"):
        review_service.create_review(
            "https://example.com/acme/demo.git",
            provider="auto",
            title="Update",
            body="Body",
            head="feature",
            base="main",
        )
