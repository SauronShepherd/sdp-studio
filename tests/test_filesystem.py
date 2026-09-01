from pathlib import Path

import pytest
from sdpstudio_server.filesystem import FileConflictError, ProjectFileSystem, UnsafePathError


def test_project_filesystem_is_relative_atomic_and_etag_checked(tmp_path: Path):
    service = ProjectFileSystem()
    info = service.write_text(tmp_path, "transformations/example.py", "print('ok')\n")
    content, loaded = service.read_text(tmp_path, "transformations/example.py")
    assert content == "print('ok')\n"
    assert loaded.etag == info.etag
    with pytest.raises(FileConflictError):
        service.write_text(tmp_path, "transformations/example.py", "changed", "stale")


def test_project_filesystem_rejects_traversal_and_binary(tmp_path: Path):
    service = ProjectFileSystem()
    with pytest.raises(UnsafePathError):
        service.resolve(tmp_path, "../outside.txt")
    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="Binary"):
        service.read_text(tmp_path, "binary.bin")
