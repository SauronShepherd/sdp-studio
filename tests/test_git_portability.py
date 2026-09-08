from pathlib import Path

from sdpstudio_server import git_service


def _commit_file(root: Path, name: str, content: str, message: str) -> None:
    (root / name).write_text(content, encoding="utf-8")
    git_service.stage(root)
    git_service.commit(root, message)


def test_annotated_tag_does_not_require_global_git_identity(tmp_path: Path):
    git_service.init(tmp_path)
    _commit_file(tmp_path, "README.md", "base\n", "initial")

    assert git_service.create_tag(tmp_path, "v1.0.0", "release") == ["v1.0.0"]


def test_conflicts_are_read_from_unmerged_index_stages(tmp_path: Path):
    git_service.init(tmp_path)
    _commit_file(tmp_path, "conflict.txt", "base\n", "initial")
    git_service.create_branch(tmp_path, "feature")
    _commit_file(tmp_path, "conflict.txt", "theirs\n", "feature")
    git_service.switch_branch(tmp_path, "main")
    _commit_file(tmp_path, "conflict.txt", "ours\n", "main")

    result = git_service._git(tmp_path, ["merge", "feature"], check=False)

    assert result.returncode != 0
    assert git_service.conflicts(tmp_path) == ["conflict.txt"]
    assert git_service.conflict_versions(tmp_path, "conflict.txt") == {
        "ours": "ours\n",
        "theirs": "theirs\n",
    }
