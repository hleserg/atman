"""Tests for scripts/codemap/renderer/system_map.py."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.codemap.renderer.system_map import (
    _replace_blocks,
    inject_marker,
    update_system_map,
)

SAMPLE_MAP = """\
# System Map

## Section 1

Some content here.

<!-- codemap:auto:start section="modules-domain-models" -->
<!-- Updated automatically by `make codemap`. Do not edit. -->
| File | Public classes | Ports |
|------|----------------|-------|
| `old_file.py` | `OldClass` | |
<!-- codemap:auto:end -->

## Section 2

More content.
"""

COMPONENTS = {
    "core-models": {"path": "src/atman/core/models", "display": "Core / Domain Models"},
}


class TestReplaceBlocks:
    def test_passes_through_unknown_section(self, tmp_path: Path) -> None:
        """Unknown sections are passed through unchanged."""
        text = textwrap.dedent("""\
            <!-- codemap:auto:start section="unknown-section" -->
            some content
            <!-- codemap:auto:end -->
        """)
        result, changed = _replace_blocks(text, tmp_path, COMPONENTS, check_mode=False)
        assert "some content" in result
        assert not changed

    def test_passes_through_ru_blocks(self, tmp_path: Path) -> None:
        """RU-language blocks are not updated."""
        text = textwrap.dedent("""\
            <!-- codemap:auto:start section="modules-domain-models" lang="ru" -->
            RU content
            <!-- codemap:auto:end -->
        """)
        result, changed = _replace_blocks(text, tmp_path, COMPONENTS, check_mode=False)
        assert "RU content" in result
        # RU blocks are never auto-updated (they need translation)
        assert not changed

    def test_no_markers_unchanged(self, tmp_path: Path) -> None:
        text = "# Just a regular doc\n\nNo markers here.\n"
        result, changed = _replace_blocks(text, tmp_path, COMPONENTS, check_mode=False)
        assert result == text
        assert not changed

    def test_check_mode_does_not_modify(self, tmp_path: Path) -> None:
        """In check mode, text is returned unchanged even if stale."""
        # Create a modules dir to make the section content non-None
        models_dir = tmp_path / "src" / "atman" / "core" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "fact.py").write_text("class FactRecord:\n    pass\n")

        text = textwrap.dedent("""\
            <!-- codemap:auto:start section="modules-domain-models" -->
            old content
            <!-- codemap:auto:end -->
        """)
        result, _changed = _replace_blocks(text, tmp_path, COMPONENTS, check_mode=True)
        # Content not changed in text (check mode only reports)
        assert "old content" in result

    def test_updates_known_section(self, tmp_path: Path) -> None:
        """A known section gets replaced with AST-generated content."""
        models_dir = tmp_path / "src" / "atman" / "core" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "fact.py").write_text('class FactRecord:\n    """Fact."""\n    pass\n')

        text = textwrap.dedent("""\
            <!-- codemap:auto:start section="modules-domain-models" -->
            old content
            <!-- codemap:auto:end -->
        """)
        result, changed = _replace_blocks(text, tmp_path, COMPONENTS, check_mode=False)
        assert changed
        assert "FactRecord" in result
        assert "old content" not in result

    def test_idempotent(self, tmp_path: Path) -> None:
        """Running twice produces no further changes."""
        models_dir = tmp_path / "src" / "atman" / "core" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "fact.py").write_text("class FactRecord:\n    pass\n")

        text = textwrap.dedent("""\
            <!-- codemap:auto:start section="modules-domain-models" -->
            <!-- codemap:auto:end -->
        """)
        first, _ = _replace_blocks(text, tmp_path, COMPONENTS, check_mode=False)
        second, changed2 = _replace_blocks(first, tmp_path, COMPONENTS, check_mode=False)
        assert not changed2
        assert first == second


class TestUpdateSystemMap:
    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        result = update_system_map(
            tmp_path / "nonexistent.md",
            tmp_path,
            COMPONENTS,
        )
        assert result is False

    def test_file_with_no_markers_unchanged(self, tmp_path: Path) -> None:
        sm = tmp_path / "SYSTEM_MAP.md"
        sm.write_text("# No markers\n")
        changed = update_system_map(sm, tmp_path, COMPONENTS)
        assert not changed
        assert sm.read_text() == "# No markers\n"

    def test_updates_file_with_marker(self, tmp_path: Path) -> None:
        models_dir = tmp_path / "src" / "atman" / "core" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "fact.py").write_text("class FactRecord:\n    pass\n")

        sm = tmp_path / "SYSTEM_MAP.md"
        sm.write_text(
            textwrap.dedent("""\
            # System Map
            <!-- codemap:auto:start section="modules-domain-models" -->
            old
            <!-- codemap:auto:end -->
        """)
        )

        changed = update_system_map(sm, tmp_path, COMPONENTS)
        assert changed
        content = sm.read_text()
        assert "FactRecord" in content
        assert "old" not in content


class TestInjectMarker:
    def test_injects_at_end_when_no_existing(self) -> None:
        text = "# Doc\n\nSome content.\n"
        result = inject_marker(text, "my-section", "table content here")
        assert 'section="my-section"' in result
        assert "table content here" in result

    def test_replaces_existing_block(self) -> None:
        text = textwrap.dedent("""\
            # Doc
            <!-- codemap:auto:start section="my-section" -->
            old content
            <!-- codemap:auto:end -->
        """)
        result = inject_marker(text, "my-section", "new content")
        assert "new content" in result
        assert "old content" not in result

    def test_lang_ru_attribute(self) -> None:
        text = "# Doc\n"
        result = inject_marker(text, "my-section", "содержимое", lang="ru")
        assert 'lang="ru"' in result
        assert "содержимое" in result
