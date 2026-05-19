"""Generate DELTA_REPORT.md comparing current AST snapshot to previous."""

from __future__ import annotations

import logging
from pathlib import Path

from ..snapshot.diff import SnapshotDiff

log = logging.getLogger(__name__)

OUTPUT_PATH = Path("docs/architecture/codemap/DELTA_REPORT.md")


def render_delta(diffs: list[SnapshotDiff], run_timestamp: str) -> str:
    non_empty = [d for d in diffs if not d.is_empty]

    lines = [
        "# Codemap Delta Report",
        "",
        f"> Generated at {run_timestamp} by `make codemap`. Do not edit.",
        "",
    ]

    if not non_empty:
        lines += ["*No changes detected since last run.*", ""]
        return "\n".join(lines)

    lines += [
        f"**{len(non_empty)} component(s) changed:**",
        "",
    ]
    for diff in non_empty:
        lines.extend(diff.to_markdown_lines())
        lines.append("")

    return "\n".join(lines)


def write_delta_report(
    diffs: list[SnapshotDiff],
    run_timestamp: str,
    repo_root: Path,
) -> bool:
    """Write DELTA_REPORT.md. Returns True if file changed."""
    output_path = repo_root / OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = render_delta(diffs, run_timestamp)
    if output_path.exists() and output_path.read_text(encoding="utf-8") == content:
        return False

    output_path.write_text(content, encoding="utf-8")
    log.info("Written %s", output_path)
    return True
