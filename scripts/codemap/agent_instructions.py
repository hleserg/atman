"""Scan docs/ and update agent instruction files with the current docs map.

Updates codemap:auto:start section="docs-structure" blocks in:
- AGENTS.md
- .cursor/rules/docs-placement.mdc
- CLAUDE.md (optional, skipped silently if marker not present)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_START_RE = re.compile(
    r'<!--\s*codemap:auto:start\s+section="(?P<section>[^"]+)"(?:\s+lang="(?P<lang>[^"]+)")?\s*-->'
)
_END_RE = re.compile(r"<!--\s*codemap:auto:end\s*-->")

TARGET_SECTION = "docs-structure"

# Files to update
AGENTS_MD = Path("AGENTS.md")
CURSOR_RULES = Path(".cursor/rules/docs-placement.mdc")
CLAUDE_MD = Path("CLAUDE.md")


def _build_docs_map(repo_root: Path, _lang: str = "en") -> str:
    """Build a markdown docs tree from the docs/ directory."""
    docs_dir = repo_root / "docs"
    if not docs_dir.exists():
        return "*docs/ directory not found.*"

    lines: list[str] = []

    def _walk(path: Path, depth: int = 0) -> None:
        indent = "  " * depth
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                lines.append(f"{indent}- **{entry.name}/**")
                _walk(entry, depth + 1)
            elif entry.suffix == ".md":
                # Show file with its first heading as description
                desc = _first_heading(entry)
                if desc:
                    lines.append(f"{indent}  - `{entry.name}` — {desc}")
                else:
                    lines.append(f"{indent}  - `{entry.name}`")

    _walk(docs_dir)

    if not lines:
        return "*No markdown files found in docs/*"

    header = "<!-- Updated automatically by `make codemap`. Do not edit. -->"
    return header + "\n" + "\n".join(lines)


def _first_heading(path: Path) -> str:
    """Return the first H1/H2 heading text from a markdown file."""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:20]:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line.startswith("## "):
                return line[3:].strip()
    except OSError:
        pass
    return ""


def _replace_section(
    text: str, section: str, new_content: str, check_mode: bool
) -> tuple[str, bool]:
    """Replace the named codemap:auto block. Returns (new_text, changed)."""
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    changed = False
    i = 0

    while i < len(lines):
        line = lines[i]
        m = _START_RE.search(line)
        if m and m.group("section") == section:
            start_line = line
            i += 1
            old_block: list[str] = []
            end_line = None
            while i < len(lines):
                if _END_RE.search(lines[i]):
                    end_line = lines[i]
                    i += 1
                    break
                old_block.append(lines[i])
                i += 1

            new_block_lines = [line + "\n" for line in new_content.splitlines()]
            old_str = "".join(old_block).strip()
            new_str = new_content.strip()

            if old_str != new_str:
                changed = True

            output.append(start_line)
            if not check_mode:
                output.extend(new_block_lines)
            else:
                output.extend(old_block)
            if end_line:
                output.append(end_line)
        else:
            output.append(line)
            i += 1

    return "".join(output), changed


def update_agent_instructions(
    repo_root: Path,
    check_mode: bool = False,
    lang: str = "en",
) -> bool:
    """Update docs-structure blocks in AGENTS.md, .cursor/rules/docs-placement.mdc, and CLAUDE.md.

    Returns True if any file was changed (or would change in check mode).
    """
    docs_map = _build_docs_map(repo_root, _lang=lang)
    any_changed = False

    targets = [
        repo_root / AGENTS_MD,
        repo_root / CURSOR_RULES,
    ]
    optional_targets = [
        repo_root / CLAUDE_MD,
    ]

    for path in targets:
        if not path.exists():
            log.warning("Target file not found: %s", path)
            continue
        original = path.read_text(encoding="utf-8")
        # Check if the section marker exists
        if TARGET_SECTION not in original:
            log.debug("Section '%s' not found in %s — skipping", TARGET_SECTION, path)
            continue
        new_text, changed = _replace_section(original, TARGET_SECTION, docs_map, check_mode)
        if changed:
            any_changed = True
            if not check_mode:
                path.write_text(new_text, encoding="utf-8")
                log.info("Updated %s (section: %s)", path, TARGET_SECTION)
            else:
                log.warning("Stale: %s (section: %s)", path, TARGET_SECTION)

    for path in optional_targets:
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        if f'section="{TARGET_SECTION}"' not in original:
            continue
        new_text, changed = _replace_section(original, TARGET_SECTION, docs_map, check_mode)
        if changed:
            any_changed = True
            if not check_mode:
                path.write_text(new_text, encoding="utf-8")
                log.info("Updated %s (section: %s)", path, TARGET_SECTION)

    return any_changed
