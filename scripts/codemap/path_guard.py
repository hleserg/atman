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


def write_text_under_root(
    path: Path,
    text: str,
    *,
    root: Path,
    encoding: str = "utf-8",
) -> None:
    """Write ``text`` only after validating ``path`` stays under ``root``."""
    safe_path = resolve_under_root(path, root=root)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(text, encoding=encoding)

