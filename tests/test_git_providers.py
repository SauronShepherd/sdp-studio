from pathlib import Path

import pytest
from sdpstudio_server import git_service, provider_reviews
from sdpstudio_server.provider_reviews import parse_remote


def test_git_text_outputs_are_bounded():
    value = git_service._bounded_text("x" * (git_service.MAX_GIT_TEXT_BYTES + 100))
    assert len(value.encode("utf-8")) <= git_service.MAX_GIT_TEXT_BYTES
    assert "SDPSTUDIO-GIT-OUTPUT-TRUNCATED" in value


def test_git_subprocess_uses_sanitized_environment(monkeypatch, tmp_path: Path):
    captured = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return Result()

    monkeypatch.setenv("SDPSTUDIO_TEST_SECRET", "must-not-leak")
    monkeypatch.setattr(git_service.subprocess, "run", fake_run)
    git_service._git(tmp_path, ["status"])
    assert "SDPSTUDIO_TEST_SECRET" not in captured["env"]
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_parse_github_and_gitlab_remotes():
    gh = parse_remote("git@github.com:acme/pipelines.git")
    assert (gh.provider, gh.owner, gh.repo) == ("github", "acme", "pipelines")
    gl = parse_remote("https://gitlab.com/data/platform/sdpstudio-demo.git")
    assert (gl.provider, gl.owner, gl.repo) == ("gitlab", "data/platform", "sdpstudio-demo")


def test_git_remote_rejects_embedded_credentials(tmp_path: Path):
    git_service.init(tmp_path)
    with pytest.raises(ValueError):
        git_service.set_remote(tmp_path, "origin", "https://user:token@example.com/org/repo.git")


def test_git_history_branch_tag_and_conflict_helpers(tmp_path: Path):
    git_service.init(tmp_path)
    (tmp_path / "README.md").write_text("first\n", encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "initial")
    assert git_service.log(tmp_path)[0]["subject"] == "initial"
    context = git_service.run_context(tmp_path)
    assert context["git_commit"]
    assert context["git_dirty"] is False
    git_service.create_branch(tmp_path, "feature")
    assert git_service.switch_branch(tmp_path, "main")["current"] == "main"
    assert git_service.create_tag(tmp_path, "v0.1.0") == ["v0.1.0"]
    assert git_service.conflicts(tmp_path) == []
    with pytest.raises(ValueError, match="current"):
        git_service.delete_branch(tmp_path, "main")


def test_git_conflict_resolution_is_explicit_and_stages_selected_side(tmp_path: Path):
    git_service.init(tmp_path)
    path = tmp_path / "conflict.txt"
    path.write_text("base\n", encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "initial")
    git_service.create_branch(tmp_path, "feature")
    path.write_text("theirs\n", encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "feature")
    git_service.switch_branch(tmp_path, "main")
    path.write_text("ours\n", encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "main")
    result = git_service._git(tmp_path, ["merge", "feature"], check=False)
    assert result.returncode != 0
    assert git_service.conflicts(tmp_path) == ["conflict.txt"]
    git_service.resolve_conflict(tmp_path, "conflict.txt", "ours")
    assert path.read_text(encoding="utf-8") == "ours\n"
    assert git_service.conflicts(tmp_path) == []
    with pytest.raises(ValueError, match="strategy"):
        git_service.resolve_conflict(tmp_path, "conflict.txt", "invalid")


def test_git_commit_does_not_implicitly_stage_unrelated_changes(tmp_path: Path):
    git_service.init(tmp_path)
    (tmp_path / "README.md").write_text("first\n", encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "initial")
    (tmp_path / "unrelated.txt").write_text("must remain unstaged\n", encoding="utf-8")
    with pytest.raises(ValueError, match="staged"):
        git_service.commit(tmp_path, "should fail")


def test_git_operations_disable_repository_hooks_and_prompting(tmp_path: Path):
    git_service.init(tmp_path)
    assert "hooksPath" in (tmp_path / ".git" / "config").read_text(encoding="utf-8")
    assert "disabled-hooks" in (tmp_path / ".git" / "config").read_text(encoding="utf-8")


def test_git_blob_reads_and_diffs_do_not_checkout(tmp_path: Path):
    git_service.init(tmp_path)
    path = tmp_path / "pipeline.json"
    path.write_text('{"version": 1}\n', encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "first")
    path.write_text('{"version": 2}\n', encoding="utf-8")
    git_service.stage(tmp_path)
    git_service.commit(tmp_path, "second")
    assert '"version": 1' in git_service.read_blob(tmp_path, "HEAD~1", "pipeline.json")
    assert '"version": 2' in git_service.read_blob(tmp_path, "HEAD", "pipeline.json")
    assert '-{"version": 1}' in git_service.blob_diff(tmp_path, "HEAD~1", "HEAD", "pipeline.json")


def test_conflict_versions_rejects_unbounded_or_empty_limits(tmp_path: Path):
    with pytest.raises(ValueError, match="Conflict version limit"):
        git_service.conflict_versions(tmp_path, "conflict.txt", 0)
    with pytest.raises(ValueError, match="Conflict version limit"):
        git_service.conflict_versions(tmp_path, "conflict.txt", git_service.MAX_GIT_TEXT_BYTES + 1)


def test_git_log_bounds_untrusted_commit_subjects(tmp_path: Path, monkeypatch):
    (tmp_path / ".git").mkdir()

    class Result:
        stdout = "a\x1fb\x1f2026-01-01T00:00:00Z\x1f" + "x" * (git_service.MAX_GIT_TEXT_BYTES + 100)

    monkeypatch.setattr(git_service, "_git", lambda *args, **kwargs: Result())
    entries = git_service.log(tmp_path)
    assert len(entries) == 1
    assert len(entries[0]["subject"].encode("utf-8")) < git_service.MAX_GIT_TEXT_BYTES


def test_git_argument_injection_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        git_service.create_branch(tmp_path, "--upload-pack=evil")
    with pytest.raises(ValueError):
        git_service.fetch(tmp_path, "--upload-pack=evil")
    with pytest.raises(ValueError):
        git_service.pull(tmp_path, "origin", "--rebase")


def test_provider_auto_detection_is_public_hosts_only():
    assert parse_remote("git@notgithub.example:org/repo.git").provider is None
    assert parse_remote("git@github.com:org/repo.git").provider == "github"
    assert parse_remote("git@gitlab.com:org/repo.git").provider == "gitlab"


def test_provider_review_listing_and_repository_metadata_use_safe_provider_endpoints(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_GITHUB_TOKEN", "test-token")
    calls = []

    def fake_request(url, payload, headers, method="POST"):
        calls.append((url, payload, headers, method))
        return [{"number": 1}] if "/pulls?" in url else {"full_name": "acme/pipelines"}

    monkeypatch.setattr(provider_reviews, "_request_json", fake_request)
    assert provider_reviews.list_provider_reviews(
        "https://github.com/acme/pipelines.git", token="test-token"
    ) == [{"number": 1}]
    assert provider_reviews.provider_repository(
        "https://github.com/acme/pipelines.git", token="test-token"
    ) == {"full_name": "acme/pipelines"}
    assert all(call[3] == "GET" and "test-token" not in call[0] for call in calls)


def test_provider_review_rejects_environment_only_credentials(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_GITHUB_TOKEN", "must-not-be-used")
    with pytest.raises(RuntimeError, match="SDPS-SECRET-001"):
        provider_reviews.list_provider_reviews("https://github.com/acme/pipelines.git")


def test_git_remote_transport_allowlist_blocks_local_and_remote_helpers():
    git_service._validate_remote_url("https://github.com/acme/pipelines.git")
    git_service._validate_remote_url("ssh://git@gitlab.com/acme/pipelines.git")
    git_service._validate_remote_url("git@github.com:acme/pipelines.git")
    with pytest.raises(ValueError):
        git_service._validate_remote_url("/tmp/repository")
    with pytest.raises(ValueError):
        git_service._validate_remote_url("ext::sh -c evil")
    with pytest.raises(ValueError):
        git_service._validate_remote_url("file:///tmp/repository")
