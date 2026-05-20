"""Track EN block content hashes for staleness detection of RU translations.

When an EN codemap block changes, any corresponding RU block is marked stale.
Hashes are stored in .codemap/en_hashes.json.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ..path_guard import write_text_under_root

log = logging.getLogger(__name__)

HASHES_FILE = Path(".codemap/en_hashes.json")


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_hashes(path: Path = HASHES_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Cannot load EN hashes from %s: %s", path, exc)
        return {}


def save_hashes(hashes: dict[str, str], path: Path = HASHES_FILE) -> None:
    repo_root = _repo_root_from(path)
    try:
        write_text_under_root(
            path,
            json.dumps(hashes, indent=2, sort_keys=True),
            root=repo_root,
        )
    except Exception as exc:
        log.warning("Cannot save EN hashes to %s: %s", path, exc)


def _repo_root_from(path: Path) -> Path:
    cur = path.resolve()
    for _ in range(12):
        if (cur / "pyproject.toml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path.cwd().resolve()


def compute_block_hash(section: str, content: str) -> str:
    """Return a short hash for a given section+content pair."""
    return _hash_content(f"{section}:{content}")


def is_stale(section: str, current_content: str, stored_hashes: dict[str, str]) -> bool:
    """Return True if the EN block has changed since the hash was stored."""
    current_hash = compute_block_hash(section, current_content)
    return stored_hashes.get(section) != current_hash


def update_hash(section: str, content: str, stored_hashes: dict[str, str]) -> None:
    stored_hashes[section] = compute_block_hash(section, content)
