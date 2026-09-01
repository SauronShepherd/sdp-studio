from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RemoteRepo:
    host: str
    owner: str
    repo: str
    provider: str | None


def parse_remote(url: str) -> RemoteRepo:
    host = ""
    path = ""
    if re.match(r"^[^@\s]+@[^:\s]+:.+$", url):
        host, path = url.split("@", 1)[1].split(":", 1)
    else:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")
    path = path.removesuffix(".git").strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or not host:
        raise ValueError("Remote must identify a repository as host/owner/repo")
    owner = "/".join(parts[:-1])
    repo = parts[-1]
    low = host.lower()
    provider = "github" if low == "github.com" else "gitlab" if low == "gitlab.com" else None
    return RemoteRepo(host=host, owner=owner, repo=repo, provider=provider)


def _request_json(
    url: str, payload: dict | None, headers: dict[str, str], method: str = "POST"
) -> dict | list:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json", "User-Agent": "SDP Studio/0.1", **headers},
        method=method,
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - provider URLs are derived from configured Git remotes
        return json.loads(response.read().decode("utf-8"))


def _provider_api(repo: RemoteRepo, provider: str, token: str | None) -> tuple[str, dict[str, str]]:
    if provider == "github":
        api = os.environ.get("SDPSTUDIO_GITHUB_API_BASE")
        if repo.host.lower() == "github.com":
            api = api or "https://api.github.com"
        elif not api or (urlparse(api).hostname or "").lower() != repo.host.lower():
            raise RuntimeError("GitHub API base must match the configured remote host")
        if not token:
            raise RuntimeError(
                "SDPS-SECRET-001: provider token must be resolved from the Studio secrets vault"
            )
        assert api is not None
        return api.rstrip("/"), {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    if provider == "gitlab":
        api = os.environ.get("SDPSTUDIO_GITLAB_API_BASE")
        if repo.host.lower() == "gitlab.com":
            api = api or "https://gitlab.com/api/v4"
        elif not api or (urlparse(api).hostname or "").lower() != repo.host.lower():
            raise RuntimeError("GitLab API base must match the configured remote host")
        if not token:
            raise RuntimeError(
                "SDPS-SECRET-001: provider token must be resolved from the Studio secrets vault"
            )
        assert api is not None
        return api.rstrip("/"), {"PRIVATE-TOKEN": token}
    raise ValueError(f"Unsupported provider: {provider}")


def list_provider_reviews(
    remote_url: str, *, provider: str = "auto", token: str | None = None
) -> list[dict]:
    repo = parse_remote(remote_url)
    selected_provider = repo.provider if provider == "auto" else provider
    api, headers = _provider_api(repo, selected_provider or "", token)
    if selected_provider == "github":
        url = f"{api}/repos/{quote(repo.owner)}/{quote(repo.repo)}/pulls?state=all&per_page=100"
    else:
        project = quote(f"{repo.owner}/{repo.repo}", safe="")
        url = f"{api}/projects/{project}/merge_requests?state=all&per_page=100"
    result = _request_json(url, None, headers, method="GET")
    return result if isinstance(result, list) else []


def provider_repository(
    remote_url: str, *, provider: str = "auto", token: str | None = None
) -> dict:
    repo = parse_remote(remote_url)
    selected_provider = repo.provider if provider == "auto" else provider
    api, headers = _provider_api(repo, selected_provider or "", token)
    if selected_provider == "github":
        url = f"{api}/repos/{quote(repo.owner)}/{quote(repo.repo)}"
    else:
        url = f"{api}/projects/{quote(f'{repo.owner}/{repo.repo}', safe='')}"
    result = _request_json(url, None, headers, method="GET")
    return cast(dict, result) if isinstance(result, dict) else {}


def create_github_pull_request(
    remote_url: str, *, title: str, body: str, head: str, base: str, token: str
) -> dict:
    repo = parse_remote(remote_url)
    if not token:
        raise RuntimeError("SDPSTUDIO_GITHUB_TOKEN is not configured")
    api = os.environ.get("SDPSTUDIO_GITHUB_API_BASE")
    if repo.host.lower() == "github.com":
        api = api or "https://api.github.com"
    else:
        if not api:
            raise RuntimeError("Self-hosted GitHub requires explicit SDPSTUDIO_GITHUB_API_BASE")
        if (urlparse(api).hostname or "").lower() != repo.host.lower():
            raise RuntimeError(
                "SDPSTUDIO_GITHUB_API_BASE host must match the configured Git remote host"
            )
    url = f"{api.rstrip('/')}/repos/{quote(repo.owner)}/{quote(repo.repo)}/pulls"
    return cast(
        dict,
        _request_json(
            url,
            {"title": title, "body": body, "head": head, "base": base},
            {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        ),
    )


def create_gitlab_merge_request(
    remote_url: str, *, title: str, body: str, head: str, base: str, token: str
) -> dict:
    repo = parse_remote(remote_url)
    if not token:
        raise RuntimeError("SDPSTUDIO_GITLAB_TOKEN is not configured")
    api = os.environ.get("SDPSTUDIO_GITLAB_API_BASE")
    if repo.host.lower() == "gitlab.com":
        api = api or "https://gitlab.com/api/v4"
    else:
        if not api:
            raise RuntimeError("Self-hosted GitLab requires explicit SDPSTUDIO_GITLAB_API_BASE")
        if (urlparse(api).hostname or "").lower() != repo.host.lower():
            raise RuntimeError(
                "SDPSTUDIO_GITLAB_API_BASE host must match the configured Git remote host"
            )
    project = quote(f"{repo.owner}/{repo.repo}", safe="")
    url = f"{api.rstrip('/')}/projects/{project}/merge_requests"
    return cast(
        dict,
        _request_json(
            url,
            {"title": title, "description": body, "source_branch": head, "target_branch": base},
            {"PRIVATE-TOKEN": token},
        ),
    )
