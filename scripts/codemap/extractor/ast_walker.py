"""AST-based Python file metadata extractor for the Living Codemap system."""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Known external packages to track as imports
KNOWN_EXTERNAL_PACKAGES = frozenset(
    {
        "cohere",
        "anthropic",
        "sentry_sdk",
        "openai",
        "pydantic",
        "pydantic_ai",
        "httpx",
        "psycopg",
        "streamlit",
        "fastapi",
        "uvicorn",
        "torch",
        "transformers",
        "FlagEmbedding",
        "click",
        "rich",
        "textual",
        "alembic",
        "sqlalchemy",
        "plotly",
        "pandas",
        "numpy",
        "sklearn",
        "huggingface_hub",
        "datasets",
        "tiktoken",
        "trafilatura",
        "duckduckgo_search",
        "pymorphy3",
        "yaml",
        "pyyaml",
    }
)


@dataclass
class ClassInfo:
    name: str
    bases: list[str]
    is_protocol: bool
    is_pydantic: bool
    docstring: str | None


@dataclass
class FunctionInfo:
    name: str
    is_cli_command: bool


@dataclass
class PortInfo:
    name: str
    methods: list[str]


@dataclass
class TodoItem:
    line: int
    kind: str  # "TODO" or "FIXME"
    text: str


@dataclass
class FileMetadata:
    path: str
    public_classes: list[ClassInfo] = field(default_factory=list)
    public_functions: list[FunctionInfo] = field(default_factory=list)
    ports: list[PortInfo] = field(default_factory=list)
    pydantic_models: list[str] = field(default_factory=list)
    cli_commands: list[str] = field(default_factory=list)
    schema_versions: list[str] = field(default_factory=list)
    todos: list[TodoItem] = field(default_factory=list)
    imports_external: list[str] = field(default_factory=list)


def _get_base_names(bases: list[ast.expr]) -> list[str]:
    """Extract string names from base class expressions."""
    names = []
    for base in bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
        elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
            # e.g. Protocol[T]
            names.append(base.value.id)
    return names


def _is_protocol(bases: list[str]) -> bool:
    return "Protocol" in bases


def _is_pydantic(bases: list[str]) -> bool:
    return any(b in ("BaseModel", "BaseSettings") for b in bases)


def _has_cli_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if function has @app.command() or @click.command() decorator."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Attribute):
                if func.attr == "command":
                    return True
            elif isinstance(func, ast.Name) and func.id == "command":
                return True
        elif isinstance(decorator, ast.Attribute):
            if decorator.attr == "command":
                return True
    return False


def _extract_todos(source_lines: list[str]) -> list[TodoItem]:
    todos = []
    for lineno, line in enumerate(source_lines, start=1):
        stripped = line.strip()
        for kind in ("TODO", "FIXME"):
            idx = stripped.find(f"# {kind}")
            if idx == -1:
                idx = stripped.find(f"#{kind}")
            if idx != -1:
                text = stripped[idx:].strip()
                todos.append(TodoItem(line=lineno, kind=kind, text=text))
                break
    return todos


def _extract_external_imports(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in KNOWN_EXTERNAL_PACKAGES:
                    found.add(top)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in KNOWN_EXTERNAL_PACKAGES:
                found.add(top)
    return sorted(found)


def walk_file(path: Path) -> FileMetadata:
    """Parse a single .py file and return its metadata."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return FileMetadata(path=str(path))

    source_lines = source.splitlines()
    meta = FileMetadata(path=str(path))

    # TODOs (comment scan — no AST needed)
    meta.todos = _extract_todos(source_lines)

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        log.warning("Syntax error in %s: %s", path, exc)
        return meta

    meta.imports_external = _extract_external_imports(tree)

    for node in ast.walk(tree):
        # Schema versions: top-level assignments SCHEMA_VERSION = "x.y.z"
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SCHEMA_VERSION":
                    meta.schema_versions.append(node.value.value)

    # Walk only top-level statements for classes and functions
    for node in tree.body:
        if isinstance(node, (ast.ClassDef,)):
            if node.name.startswith("_"):
                continue
            bases = _get_base_names(node.bases)
            is_prot = _is_protocol(bases)
            is_pyd = _is_pydantic(bases)
            docstring = ast.get_docstring(node)

            cls_info = ClassInfo(
                name=node.name,
                bases=bases,
                is_protocol=is_prot,
                is_pydantic=is_pyd,
                docstring=docstring,
            )
            meta.public_classes.append(cls_info)

            if is_pyd:
                meta.pydantic_models.append(node.name)

            if is_prot:
                # Extract method names from the protocol
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        not item.name.startswith("_") or item.name == "__init__"
                    ):
                        methods.append(item.name)
                meta.ports.append(PortInfo(name=node.name, methods=methods))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            is_cli = _has_cli_decorator(node)
            meta.public_functions.append(FunctionInfo(name=node.name, is_cli_command=is_cli))
            if is_cli:
                meta.cli_commands.append(node.name)

    return meta


def walk_directory(path: Path) -> list[FileMetadata]:
    """Recursively walk a directory and return metadata for all .py files."""
    if not path.exists() or not path.is_dir():
        return []
    results = []
    for py_file in sorted(path.rglob("*.py")):
        if py_file.name.startswith("_") and py_file.name != "__init__.py":
            # still include _*.py but they'll have no public exports
            pass
        results.append(walk_file(py_file))
    return results
