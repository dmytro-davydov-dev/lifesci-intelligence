from pathlib import Path

import pytest

from app.infrastructure.storage import InvalidStorageKeyError, LocalFileStorage


def test_save_uses_random_keys_and_roundtrips(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    first = storage.save(b"same", ".txt")
    second = storage.save(b"same", ".txt")

    assert first != second
    assert storage.path_for(first).read_bytes() == b"same"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([first, second])


def test_delete_removes_file(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    key = storage.save(b"data", ".pdf")
    storage.delete(key)
    assert not storage.path_for(key).exists()


@pytest.mark.parametrize(
    "key", ["../secret.txt", "/etc/passwd", "abc.txt", "0" * 32 + ".exe", "0" * 32 + ".txt/.."]
)
def test_rejects_keys_outside_expected_format(tmp_path: Path, key: str) -> None:
    with pytest.raises(InvalidStorageKeyError):
        LocalFileStorage(tmp_path).path_for(key)
