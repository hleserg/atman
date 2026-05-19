"""i18n helpers — mark stale RU blocks and prepare for translation."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..snapshot.en_hashes import compute_block_hash, load_hashes, save_hashes

log = logging.getLogger(__name__)

_START_EN_RE = re.compile(r'<!--\s*codemap:auto:start\s+section="(?P<section>[^"]+)"\s*-->')
_START_RU_RE = re.compile(
    r'<!--\s*codemap:auto:start\s+section="(?P<section>[^"]+)"\s+lang="ru"\s*-->'
)
_END_RE = re.compile(r"<!--\s*codemap:auto:end\s*-->")

STALE_COMMENT = "<!-- codemap:stale:ru — needs translation -->"


def _extract_blocks(text: str, lang: str = "en") -> dict[str, str]:
    """Extract {section_name: content} for blocks matching lang."""
    pattern = _START_RU_RE if lang == "ru" else _START_EN_RE
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        m = pattern.search(lines[i])
        if m:
            section = m.group("section")
            i += 1
            content_lines: list[str] = []
            while i < len(lines):
                if _END_RE.search(lines[i]):
                    i += 1
                    break
                content_lines.append(lines[i])
                i += 1
            blocks[section] = "".join(content_lines)
        else:
            i += 1
    return blocks


def flag_stale_ru_blocks(
    en_path: Path,
    ru_path: Path,
    hashes_file: Path | None = None,
) -> list[str]:
    """Scan EN + RU pair, return list of stale section names."""
    if not en_path.exists() or not ru_path.exists():
        return []

    stored = load_hashes(hashes_file) if hashes_file else {}
    en_text = en_path.read_text(encoding="utf-8")
    en_blocks = _extract_blocks(en_text, lang="en")

    stale_sections: list[str] = []
    for section, content in en_blocks.items():
        h = compute_block_hash(section, content)
        if stored.get(section) != h:
            stale_sections.append(section)

    return stale_sections


def update_en_hashes(
    en_path: Path,
    hashes_file: Path,
) -> None:
    """Recompute and save EN block hashes after a successful EN update."""
    if not en_path.exists():
        return
    en_text = en_path.read_text(encoding="utf-8")
    en_blocks = _extract_blocks(en_text, lang="en")
    stored = load_hashes(hashes_file)
    for section, content in en_blocks.items():
        stored[section] = compute_block_hash(section, content)
    save_hashes(stored, hashes_file)
    log.info("Updated EN hashes in %s", hashes_file)
