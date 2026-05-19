"""Tests for scripts/codemap/extractor/ast_walker.py."""

from __future__ import annotations

# Make scripts importable
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.codemap.extractor.ast_walker import (
    FileMetadata,
    walk_directory,
    walk_file,
)


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


class TestWalkFile:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write_py(tmp_path, "empty.py", "")
        meta = walk_file(p)
        assert meta.public_classes == []
        assert meta.public_functions == []
        assert meta.todos == []

    def test_public_class_extracted(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "models.py",
            """\
            class MyModel:
                pass
            """,
        )
        meta = walk_file(p)
        assert len(meta.public_classes) == 1
        assert meta.public_classes[0].name == "MyModel"

    def test_private_class_excluded(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "models.py",
            """\
            class _PrivateModel:
                pass
            """,
        )
        meta = walk_file(p)
        assert meta.public_classes == []

    def test_pydantic_model_detected(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "models.py",
            """\
            from pydantic import BaseModel

            class Fact(BaseModel):
                content: str
            """,
        )
        meta = walk_file(p)
        assert "Fact" in meta.pydantic_models
        assert meta.public_classes[0].is_pydantic is True

    def test_protocol_class_detected(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "port.py",
            """\
            from typing import Protocol

            class MemoryPort(Protocol):
                def store(self, data: str) -> None: ...
                def retrieve(self, key: str) -> str: ...
            """,
        )
        meta = walk_file(p)
        assert len(meta.ports) == 1
        port = meta.ports[0]
        assert port.name == "MemoryPort"
        assert "store" in port.methods
        assert "retrieve" in port.methods

    def test_todo_extracted(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "service.py",
            """\
            def foo():
                # TODO: implement this
                pass

            def bar():
                # FIXME: broken
                pass
            """,
        )
        meta = walk_file(p)
        kinds = [t.kind for t in meta.todos]
        assert "TODO" in kinds
        assert "FIXME" in kinds

    def test_schema_version_extracted(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "models.py",
            """\
            SCHEMA_VERSION = "2.0.0"

            class Fact:
                pass
            """,
        )
        meta = walk_file(p)
        assert "2.0.0" in meta.schema_versions

    def test_cli_command_detected(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "cli.py",
            """\
            import click

            @click.command()
            def my_command():
                pass
            """,
        )
        meta = walk_file(p)
        assert "my_command" in meta.cli_commands

    def test_external_imports_detected(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "adapter.py",
            """\
            import anthropic
            from pydantic import BaseModel
            """,
        )
        meta = walk_file(p)
        assert "anthropic" in meta.imports_external
        assert "pydantic" in meta.imports_external

    def test_public_function_extracted(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "utils.py",
            """\
            def public_fn():
                pass

            def _private_fn():
                pass
            """,
        )
        meta = walk_file(p)
        names = [f.name for f in meta.public_functions]
        assert "public_fn" in names
        assert "_private_fn" not in names

    def test_syntax_error_returns_partial(self, tmp_path: Path) -> None:
        p = _write_py(tmp_path, "bad.py", "def broken(:")
        meta = walk_file(p)
        # Should return partial (TODOs may still be extracted)
        assert isinstance(meta, FileMetadata)

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        meta = walk_file(tmp_path / "nonexistent.py")
        assert meta.public_classes == []

    def test_docstring_extracted(self, tmp_path: Path) -> None:
        p = _write_py(
            tmp_path,
            "models.py",
            '''\
            class Documented:
                """A well-documented class."""
                pass

            class Undocumented:
                pass
            ''',
        )
        meta = walk_file(p)
        docs = {c.name: c.docstring for c in meta.public_classes}
        assert docs["Documented"] == "A well-documented class."
        assert docs["Undocumented"] is None


class TestWalkDirectory:
    def test_empty_dir(self, tmp_path: Path) -> None:
        result = walk_directory(tmp_path)
        assert result == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        result = walk_directory(tmp_path / "no_such")
        assert result == []

    def test_walks_py_files(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "class A: pass")
        _write_py(tmp_path, "b.py", "class B: pass")
        (tmp_path / "readme.md").write_text("# doc")

        results = walk_directory(tmp_path)
        names = [Path(m.path).name for m in results]
        assert "a.py" in names
        assert "b.py" in names
        assert "readme.md" not in names

    def test_walks_subdirs(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        _write_py(sub, "nested.py", "class Nested: pass")

        results = walk_directory(tmp_path)
        names = [Path(m.path).name for m in results]
        assert "nested.py" in names

    def test_real_core_models(self) -> None:
        """Walk the actual core/models/ directory from the repo."""
        repo_root = Path(__file__).parent.parent.parent
        models_dir = repo_root / "src" / "atman" / "core" / "models"
        if not models_dir.exists():
            pytest.skip("core/models not found")

        results = walk_directory(models_dir)
        assert len(results) > 0
        all_classes = [c.name for fm in results for c in fm.public_classes]
        # At least some known classes should be present
        assert any(c in all_classes for c in ["FactRecord", "Identity", "SessionExperience"])
