"""Provider-review orchestration independent of FastAPI request handling."""

from __future__ import annotations

from typing import Any

from .provider_reviews import create_github_pull_request, create_gitlab_merge_request, parse_remote


def create_review(
    remote_url: str,
    *,
    provider: str,
    title: str,
    body: str,
    head: str,
    base: str,
    token: str | None = None,
) -> dict[str, Any]:
    selected = parse_remote(remote_url).provider if provider == "auto" else provider
    if selected == "github":
        result = create_github_pull_request(
            remote_url, title=title, body=body, head=head, base=base, token=token or ""
        )
        return {
            "provider": "github",
            "url": result.get("html_url"),
            "number": result.get("number"),
            "raw": result,
        }
    if selected == "gitlab":
        result = create_gitlab_merge_request(
            remote_url, title=title, body=body, head=head, base=base, token=token or ""
        )
        return {
            "provider": "gitlab",
            "url": result.get("web_url"),
            "number": result.get("iid"),
            "raw": result,
        }
    raise ValueError(
        "Remote is not recognized as GitHub/GitLab; use generic Git push or specify a supported provider"
    )
