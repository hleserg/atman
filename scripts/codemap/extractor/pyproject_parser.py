"""Parse pyproject.toml for project metadata useful in codemap reports."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class PyprojectInfo:
    name: str = ""
    version: str = ""
    python_requires: str = ""
    dependencies: list[str] = field(default_factory=list)
    optional_deps: dict[str, list[str]] = field(default_factory=dict)
    scripts: dict[str, str] = field(default_factory=dict)
    test_paths: list[str] = field(default_factory=list)


def parse_pyproject(path: Path) -> PyprojectInfo:
    """Parse pyproject.toml and return structured info."""
    if not path.exists():
        return PyprojectInfo()

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            log.warning("No TOML parser available (need Python 3.11+ or pip install tomli)")
            return PyprojectInfo()

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to parse %s: %s", path, exc)
        return PyprojectInfo()

    project = data.get("project", {})
    info = PyprojectInfo(
        name=project.get("name", ""),
        version=project.get("version", ""),
        python_requires=project.get("requires-python", ""),
        dependencies=project.get("dependencies", []),
        optional_deps=project.get("optional-dependencies", {}),
        scripts=project.get("scripts", {}),
    )

    # Extract test paths from pytest config
    pytest_cfg = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    info.test_paths = pytest_cfg.get("testpaths", [])

    return info
