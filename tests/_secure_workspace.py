"""Private workspace directories for subprocess tests (Sonar S5443)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def secure_workspace(prefix: str = "atman-test-ws-") -> Iterator[Path]:
    """Yield a private temp directory with restrictive permissions."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        os.chmod(path, 0o700)
        yield path
    finally:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
