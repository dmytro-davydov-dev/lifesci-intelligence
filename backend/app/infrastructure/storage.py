"""Local file storage addressed by random keys (never by user-supplied paths)."""

import os
import re
import tempfile
import uuid
from pathlib import Path

_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.(pdf|txt|md)$")


class InvalidStorageKeyError(ValueError):
    pass


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def save(self, data: bytes, extension: str) -> str:
        key = f"{uuid.uuid4().hex}{extension}"
        target = self.path_for(key)
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self.root, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return key

    def path_for(self, key: str) -> Path:
        if not _KEY_PATTERN.fullmatch(key):
            raise InvalidStorageKeyError("Invalid storage key.")
        return self.root / key

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)
