"""Update codemap:auto blocks in SYSTEM_MAP.md from AST data."""

from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path

from ..extractor.ast_walker import FileMetadata, walk_directory

log = logging.getLogger(__name__)

# Marker pattern
_START_RE = re.compile(
    r'<!--\s*codemap:auto:start\s+section="(?P<section>[^"]+)"(?:\s+lang="(?P<lang>[^"]+)")?\s*-->'
)
_END_RE = re.compile(r"<!--\s*codemap:auto:end\s*-->")


def _render_modules_table(files: list[FileMetadata], repo_root: Path) -> str:
    """Generate a markdown table from file metadata."""
    lines = ["| File | Public classes | Ports |", "|------|----------------|-------|"]
    for fm in files:
        if not fm.public_classes and not fm.ports:
            continue
        rel = Path(fm.path)
        with contextlib.suppress(ValueError):
            rel = rel.relative_to(repo_root / "src" / "atman")
        classes = ", ".join(f"`{c.name}`" for c in fm.public_classes[:6])
        ports = ", ".join(f"`{p.name}`" for p in fm.ports[:4])
        lines.append(f"| `{rel}` | {classes} | {ports} |")
    if len(lines) == 2:
        lines.append("| *(none)* | — | — |")
    return "\n".join(lines)


def _render_port_adapter_matrix(
    port_files: list[FileMetadata],
    adapter_files: list[FileMetadata],
) -> str:
    """Cross-reference ports vs adapters."""
    port_names = []
    for fm in port_files:
        for p in fm.ports:
            port_names.append(p.name)

    adapter_impl: dict[str, list[str]] = {p: [] for p in port_names}
    for fm in adapter_files:
        for cls in fm.public_classes:
            for port in port_names:
                # heuristic: adapter class name contains port name stem or bases reference it
                port_stem = port.replace("Port", "").replace("Store", "").replace("ABC", "")
                if port_stem.lower() in cls.name.lower() or port in cls.bases:
                    adapter_impl[port].append(cls.name)

    if not port_names:
        return "*No ports found.*"

    lines = ["| Port | Implementations |", "|------|----------------|"]
    for port in port_names:
        impls = adapter_impl.get(port, [])
        impl_str = ", ".join(f"`{i}`" for i in impls[:5]) if impls else "*(none)*"
        lines.append(f"| `{port}` | {impl_str} |")
    return "\n".join(lines)


def _render_todos_table(
    components: dict[str, list[FileMetadata]],
) -> str:
    lines = ["| Component | TODO count | FIXME count |", "|-----------|------------|-------------|"]
    for name, files in components.items():
        todos = sum(len([t for t in fm.todos if t.kind == "TODO"]) for fm in files)
        fixmes = sum(len([t for t in fm.todos if t.kind == "FIXME"]) for fm in files)
        lines.append(f"| `{name}` | {todos} | {fixmes} |")
    return "\n".join(lines)


def _build_section_content(
    section: str,
    repo_root: Path,
    components: dict,
) -> str | None:
    """Build content string for a given section name."""
    src = repo_root / "src" / "atman"

    if section == "modules-domain-models":
        files = walk_directory(src / "core" / "models")
        return _render_modules_table(files, repo_root)

    if section == "modules-ports":
        files = walk_directory(src / "core" / "ports")
        return _render_modules_table(files, repo_root)

    if section == "modules-services":
        files = walk_directory(src / "core" / "services")
        return _render_modules_table(files, repo_root)

    if section == "modules-adapters":
        files = walk_directory(src / "adapters")
        return _render_modules_table(files, repo_root)

    if section == "port-adapter-matrix":
        port_files = walk_directory(src / "core" / "ports")
        adapter_files = walk_directory(src / "adapters")
        return _render_port_adapter_matrix(port_files, adapter_files)

    if section == "todos":
        comp_files: dict[str, list[FileMetadata]] = {}
        for comp_id, comp_cfg in components.items():
            path = repo_root / comp_cfg["path"]
            comp_files[comp_id] = walk_directory(path)
        return _render_todos_table(comp_files)

    return None  # section not handled


def _replace_blocks(
    text: str, repo_root: Path, components: dict, check_mode: bool
) -> tuple[str, bool]:
    """Replace all codemap:auto blocks in text. Returns (new_text, changed)."""
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    changed = False
    i = 0

    while i < len(lines):
        line = lines[i]
        m = _START_RE.search(line)
        if m:
            section = m.group("section")
            lang = m.group("lang") or "en"

            # Collect lines until end marker
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
                # Don't auto-update non-EN blocks (they need translation)
                output.append(start_line)
                output.extend(old_block)
                if end_line:
                    output.append(end_line)
                continue

            new_content = _build_section_content(section, repo_root, components)
            if new_content is None:
                # Pass through unchanged
                output.append(start_line)
                output.extend(old_block)
                if end_line:
                    output.append(end_line)
                continue

            # Build new block
            header_line = "<!-- Updated automatically by `make codemap`. Do not edit. -->\n"
            new_block_lines = [header_line] + [ln + "\n" for ln in new_content.splitlines()]

            # Compare ignoring trailing whitespace
            old_content = "".join(old_block).strip()
            new_content_full = "".join(new_block_lines).strip()

            if old_content != new_content_full:
                changed = True
                if check_mode:
                    log.warning("Section '%s' is stale (would be updated)", section)

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


def update_system_map(
    system_map_path: Path,
    repo_root: Path,
    components: dict,
    check_mode: bool = False,
) -> bool:
    """Update (or check) codemap:auto blocks in SYSTEM_MAP.md.

    Returns True if the file was changed (or would be changed in check mode).
    """
    if not system_map_path.exists():
        log.warning("SYSTEM_MAP.md not found at %s", system_map_path)
        return False

    original = system_map_path.read_text(encoding="utf-8")
    new_text, changed = _replace_blocks(original, repo_root, components, check_mode)

    if changed and not check_mode:
        system_map_path.write_text(new_text, encoding="utf-8")
        log.info("Updated %s", system_map_path)

    return changed


def inject_marker(text: str, section: str, content: str, lang: str = "en") -> str:
    """Inject or replace a codemap:auto block for a given section."""
    lang_attr = f' lang="{lang}"' if lang != "en" else ""
    start = f'<!-- codemap:auto:start section="{section}"{lang_attr} -->'
    end = "<!-- codemap:auto:end -->"

    header = "<!-- Updated automatically by `make codemap`. Do not edit. -->"
    block = f"{start}\n{header}\n{content}\n{end}"

    # Replace existing block if present
    pattern = re.compile(
        re.escape(f'<!-- codemap:auto:start section="{section}"{lang_attr} -->')
        + r".*?"
        + re.escape("<!-- codemap:auto:end -->"),
        re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(block, text)
    return text + "\n" + block + "\n"
