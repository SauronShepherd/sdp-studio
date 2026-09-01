import pytest
from sdpstudio_server.filesystem import FileConflictError, ProjectFileSystem


def test_filesystem_mutations_are_safe_and_etag_checked(tmp_path):
    fs = ProjectFileSystem()
    fs.create_directory(tmp_path, "notes")
    info = fs.write_text(tmp_path, "notes/a.txt", "hello")
    renamed = fs.rename(tmp_path, "notes/a.txt", "notes/b.txt", info.etag)
    assert renamed.path == "notes/b.txt"
    with pytest.raises(FileConflictError):
        fs.delete(tmp_path, "notes/b.txt", "stale")
    fs.delete(tmp_path, "notes/b.txt", renamed.etag)
    fs.delete(tmp_path, "notes")


def test_filesystem_mutations_reject_git_internals(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="Git internals"):
        ProjectFileSystem().create_directory(tmp_path, ".git/hooks")
