"""Update README.md codemap:auto blocks with component status and stats."""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_START_RE = re.compile(
    r'<!--\s*codemap:auto:start\s+section="(?P<section>[^"]+)"(?:\s+lang="(?P<lang>[^"]+)")?\s*-->'
)
_END_RE = re.compile(r"<!--\s*codemap:auto:end\s*-->")


def _count_tests(repo_root: Path) -> int:
    """Count test functions in tests/ directory."""
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return 0
    count = 0
    for f in tests_dir.rglob("test_*.py"):
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            count += src.count("def test_")
        except OSError:
            pass
    return count


def _component_status(comp_cfg: dict, repo_root: Path) -> str:
    """Return ✅, 🚧, or ⏳ based on component existence and adapter count."""
    path = repo_root / comp_cfg["path"]
    if not path.exists():
        return "⏳"

    py_files = list(path.rglob("*.py"))
    non_stub = [f for f in py_files if not f.name.startswith("_") or f.name == "__init__.py"]
    # Check if any file has at least 1 class (not just a stub)
    has_impl = False
    for f in non_stub[:10]:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            if "class " in src and len(src) > 200:
                has_impl = True
                break
        except OSError:
            pass

    if has_impl:
        return "✅"
    return "🚧"


def _render_roadmap_status(components: dict, repo_root: Path) -> str:
    lines = ["| Component | Status | Path |", "|-----------|--------|------|"]
    for comp_id, cfg in components.items():
        status = _component_status(cfg, repo_root)
        display = cfg.get("display", comp_id)
        path = cfg["path"]
        lines.append(f"| {display} | {status} | `{path}` |")
    return "\n".join(lines)


def _render_test_stats(repo_root: Path) -> str:
    count = _count_tests(repo_root)
    return f"**Tests:** {count} test functions found in `tests/` directory."


def _build_section_content(section: str, components: dict, repo_root: Path) -> str | None:
    if section == "roadmap-status":
        return _render_roadmap_status(components, repo_root)
    if section == "ready-components":
        lines = []
        for comp_id, cfg in components.items():
            status = _component_status(cfg, repo_root)
            display = cfg.get("display", comp_id)
            lines.append(f"- {status} **{display}** (`{cfg['path']}`)")
        return "\n".join(lines)
    if section == "test-stats":
        return _render_test_stats(repo_root)
    return None


def update_readme(
    readme_path: Path,
    repo_root: Path,
    components: dict,
    check_mode: bool = False,
) -> bool:
    """Update codemap:auto blocks in README.md. Returns True if changed."""
    if not readme_path.exists():
        log.warning("README.md not found at %s", readme_path)
        return False

    original = readme_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    output: list[str] = []
    changed = False
    i = 0

    while i < len(lines):
        line = lines[i]
        m = _START_RE.search(line)
        if m:
            section = m.group("section")
            lang = m.group("lang") or "en"
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

            if lang != "en":
                output.append(start_line)
                output.extend(old_block)
                if end_line:
                    output.append(end_line)
                continue

            new_content = _build_section_content(section, components, repo_root)
            if new_content is None:
                output.append(start_line)
                output.extend(old_block)
                if end_line:
                    output.append(end_line)
                continue

            header = "<!-- Updated automatically by `make codemap`. Do not edit. -->\n"
            new_block_lines = [header] + [ln + "\n" for ln in new_content.splitlines()]
            old_str = "".join(old_block).strip()
            new_str = "".join(new_block_lines).strip()

            if old_str != new_str:
                changed = True
                if check_mode:
                    log.warning("README section '%s' is stale", section)

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

    new_text = "".join(output)
    if changed and not check_mode:
        readme_path.write_text(new_text, encoding="utf-8")
        log.info("Updated %s", readme_path)

    return changed
