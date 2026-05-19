"""Classify .md files as misplaced based on filename/content rules.

Output: .codemap/misplaced.json
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MISPLACED_FILE = Path(".codemap/misplaced.json")


@dataclass
class MisplacedDoc:
    path: str
    reason: str
    suggested_location: str
    confidence: float  # 0.0..1.0


# Rules: (pattern_to_match, reason, suggested_location, confidence)
# pattern_to_match is tested against the relative path
_RULES: list[tuple[re.Pattern, str, str, float]] = [
    # ADR files not in docs/architecture/ADR/
    (
        re.compile(r"(^|/)ADR[-_]\d+", re.IGNORECASE),
        "ADR files belong in docs/architecture/ADR/",
        "docs/architecture/ADR/",
        0.92,
    ),
    # Design docs not in docs/design/
    (
        re.compile(r"(^|/)DESIGN_", re.IGNORECASE),
        "Design docs belong in docs/design/",
        "docs/design/",
        0.90,
    ),
    # Work packages not in docs/development/work-packages/
    (
        re.compile(r"(^|/)WP[-_]\d+", re.IGNORECASE),
        "Work package docs belong in docs/development/work-packages/",
        "docs/development/work-packages/",
        0.90,
    ),
    # Runbooks not in docs/ops/
    (
        re.compile(r"(^|/)RUNBOOK", re.IGNORECASE),
        "Runbooks belong in docs/ops/",
        "docs/ops/",
        0.88,
    ),
    # Research docs not in docs/research/
    (
        re.compile(r"(^|/)RESEARCH[-_]", re.IGNORECASE),
        "Research docs belong in docs/research/",
        "docs/research/",
        0.85,
    ),
    # Docs in repo root (except allowed files) — only single-component paths
    (
        re.compile(
            r"^(?!README|MANIFEST|AGENTS|CLAUDE|LICENSE|CHANGELOG|CONTRIBUTING)[^/\\]+\.md$",
            re.IGNORECASE,
        ),
        "Docs in repo root should be under docs/ (except README/MANIFEST/AGENTS/CLAUDE)",
        "docs/",
        0.75,
    ),
    # Feature READMEs not in docs/features/
    (
        re.compile(r"(^|/)features/(?!.*/README)", re.IGNORECASE),
        "Feature docs should be in docs/features/<slug>/README.md",
        "docs/features/",
        0.80,
    ),
]

# Allowed root-level md files
_ALLOWED_ROOT = frozenset(
    {
        "README.md",
        "README-ru.md",
        "MANIFEST.md",
        "MANIFEST-ru.md",
        "AGENTS.md",
        "CLAUDE.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
    }
)


def _is_allowed_root(rel: Path) -> bool:
    return len(rel.parts) == 1 and rel.name in _ALLOWED_ROOT


def classify_docs(repo_root: Path) -> list[MisplacedDoc]:
    """Scan all .md files and classify potentially misplaced ones."""
    misplaced: list[MisplacedDoc] = []

    # Files to exclude from scanning
    exclude_dirs = {".git", ".venv", "node_modules", "__pycache__", ".codemap"}

    for md_file in repo_root.rglob("*.md"):
        try:
            rel = md_file.relative_to(repo_root)
        except ValueError:
            continue
        # Skip excluded dirs (check relative parts to avoid false positives from absolute path)
        if any(part in exclude_dirs for part in rel.parts):
            continue

        rel_str = str(rel)

        # Skip files already in the right place
        if str(rel).startswith("docs/"):
            continue

        # Skip allowed root files
        if _is_allowed_root(rel):
            continue

        # Check against rules
        for pattern, reason, suggested, confidence in _RULES:
            if pattern.search(rel_str):
                misplaced.append(
                    MisplacedDoc(
                        path=rel_str,
                        reason=reason,
                        suggested_location=suggested,
                        confidence=confidence,
                    )
                )
                break  # First matching rule wins

    return misplaced


def write_misplaced_json(misplaced: list[MisplacedDoc], repo_root: Path) -> None:
    output = repo_root / MISPLACED_FILE
    output.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(m) for m in misplaced]
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Written %s (%d entries)", output, len(data))


def apply_high_confidence_moves(
    misplaced: list[MisplacedDoc],
    repo_root: Path,
    threshold: float = 0.90,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Move high-confidence misplaced docs. Returns list of (from, to) pairs."""
    moves: list[tuple[str, str]] = []

    for doc in misplaced:
        if doc.confidence < threshold:
            continue
        src = repo_root / doc.path
        dest_dir = repo_root / doc.suggested_location
        dest = dest_dir / src.name

        if not src.exists():
            continue

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                log.warning("Skipping move: destination already exists: %s", dest)
                continue
            src.rename(dest)
            log.info("Moved %s → %s", src, dest)

        moves.append((doc.path, str(dest.relative_to(repo_root))))

    return moves
