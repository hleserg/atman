"""Phase 2: Translate stale RU codemap blocks using Anthropic API.

Usage:
    python -m scripts.codemap translate --lang ru --only-stale

Requires ANTHROPIC_API_KEY env var. Uses `anthropic` SDK (already in pyproject deps).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .path_guard import write_text_under_root
from .renderer.i18n import _END_RE, _START_RU_RE, flag_stale_ru_blocks
from .snapshot.en_hashes import load_hashes, save_hashes

log = logging.getLogger(__name__)


def _repo_root_from(path: Path) -> Path:
    cur = path.resolve()
    for _ in range(12):
        if (cur / "pyproject.toml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    msg = f"Cannot locate repo root from {path!s}"
    raise ValueError(msg)


def _translate_block(en_content: str, section: str) -> str:
    """Call Anthropic API to translate an EN codemap block to Russian."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot translate")

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. pip install anthropic") from None

    client = anthropic.Anthropic(api_key=api_key)

    prompt = (
        f"Translate the following technical documentation block (section: `{section}`) "
        f"from English to Russian. Preserve all markdown formatting, code blocks, "
        f"table structure, and technical terms (class names, file paths, etc.) verbatim. "
        f"Only translate prose text.\n\n"
        f"---\n{en_content}\n---"
    )

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text  # type: ignore[index]


def _replace_ru_block(text: str, section: str, new_content: str) -> tuple[str, bool]:
    """Replace the RU block for a given section with new_content.

    Returns (updated_text, replaced) where replaced is False if no matching
    lang="ru" block was found (translation generated but cannot be inserted).
    """
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    replaced = False
    i = 0
    while i < len(lines):
        m = _START_RU_RE.search(lines[i])
        if m and m.group("section") == section:
            start_line = lines[i]
            i += 1
            end_line: str | None = None
            while i < len(lines):
                if _END_RE.search(lines[i]):
                    end_line = lines[i]
                    i += 1
                    break
                i += 1
            output.append(start_line)
            header = "<!-- Updated automatically by `make codemap translate`. Do not edit. -->\n"
            output.append(header)
            for ln in new_content.splitlines():
                output.append(ln + "\n")
            if end_line:
                output.append(end_line)
            replaced = True
        else:
            output.append(lines[i])
            i += 1
    return "".join(output), replaced


def translate_stale_blocks(
    en_path: Path,
    ru_path: Path,
    only_stale: bool = True,
    hashes_file: Path | None = None,
) -> list[str]:
    """Translate stale EN→RU blocks. Returns list of translated section names."""
    if not en_path.exists() or not ru_path.exists():
        log.warning("EN or RU file not found: %s / %s", en_path, ru_path)
        return []

    if only_stale:
        stale_sections = flag_stale_ru_blocks(en_path, ru_path, hashes_file)
        if not stale_sections:
            log.info("No stale RU blocks found in %s", ru_path)
            return []
    else:
        # Translate all sections
        from .renderer.i18n import _START_EN_RE

        en_text = en_path.read_text(encoding="utf-8")

        def _extract_en(text: str) -> dict[str, str]:
            blocks: dict[str, str] = {}
            lns = text.splitlines(keepends=True)
            i = 0
            while i < len(lns):
                m = _START_EN_RE.search(lns[i])
                if m:
                    section = m.group("section")
                    i += 1
                    content_lines: list[str] = []
                    while i < len(lns):
                        if _END_RE.search(lns[i]):
                            i += 1
                            break
                        content_lines.append(lns[i])
                        i += 1
                    blocks[section] = "".join(content_lines)
                else:
                    i += 1
            return blocks

        stale_sections = list(_extract_en(en_path.read_text(encoding="utf-8")).keys())

    en_text = en_path.read_text(encoding="utf-8")

    # Extract EN block contents
    from .renderer.i18n import _START_EN_RE

    def _extract_en_blocks(text: str) -> dict[str, str]:
        blocks: dict[str, str] = {}
        lns = text.splitlines(keepends=True)
        i = 0
        while i < len(lns):
            m = _START_EN_RE.search(lns[i])
            if m:
                section = m.group("section")
                i += 1
                content_lines: list[str] = []
                while i < len(lns):
                    if _END_RE.search(lns[i]):
                        i += 1
                        break
                    content_lines.append(lns[i])
                    i += 1
                blocks[section] = "".join(content_lines)
            else:
                i += 1
        return blocks

    en_blocks = _extract_en_blocks(en_text)
    ru_text = ru_path.read_text(encoding="utf-8")
    translated: list[str] = []

    for section in stale_sections:
        en_content = en_blocks.get(section, "")
        if not en_content.strip():
            continue
        log.info("Translating section '%s' in %s", section, ru_path)
        try:
            ru_content = _translate_block(en_content.strip(), section)
            ru_text, replaced = _replace_ru_block(ru_text, section, ru_content)
            if replaced:
                translated.append(section)
            else:
                log.warning("No lang='ru' block found for section '%s' in %s", section, ru_path)
        except Exception as exc:
            log.error("Failed to translate section '%s': %s", section, exc)

    if translated:
        repo_root = _repo_root_from(en_path)
        write_text_under_root(ru_path, ru_text, root=repo_root)
        log.info("Updated %s (%d sections)", ru_path, len(translated))

        # Update hashes
        if hashes_file:
            stored = load_hashes(hashes_file)
            from .snapshot.en_hashes import compute_block_hash

            for section in translated:
                if section in en_blocks:
                    stored[section] = compute_block_hash(section, en_blocks[section])
            save_hashes(stored, hashes_file)

    return translated
