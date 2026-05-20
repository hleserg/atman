"""Guard filesystem paths against traversal outside a trusted root (Sonar S2083)."""

from __future__ import annotations

from pathlib import Path


def resolve_under_root(path: Path, *, root: Path) -> Path:
    """Resolve ``path`` and ensure it stays under ``root``."""
    resolved = path.expanduser().resolve()
    root_resolved = root.expanduser().resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        msg = f"Path {path!s} escapes trusted root {root!s}"
        raise ValueError(msg)
    return resolved
