"""Scan configuration for environment variable definitions.

Since there is no .env.example, we scan src/atman/config.py for
typed Pydantic settings fields and their descriptions.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class EnvVar:
    name: str  # Python field name (converted to ENV_VAR_NAME form)
    env_name: str  # Actual env var name
    type_hint: str
    default: str | None
    description: str | None


def scan_config_file(config_path: Path) -> list[EnvVar]:
    """Extract env vars from a Pydantic settings file."""
    if not config_path.exists():
        return []

    try:
        source = config_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(config_path))
    except (OSError, SyntaxError) as exc:
        log.warning("Cannot parse %s: %s", config_path, exc)
        return []

    env_vars: list[EnvVar] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Look for classes that have BaseSettings or similar in bases
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(base.attr)

        is_settings = any("Settings" in b or b in ("BaseSettings", "BaseModel") for b in base_names)
        if not is_settings:
            continue

        for item in node.body:
            if not isinstance(item, ast.AnnAssign):
                continue
            if not isinstance(item.target, ast.Name):
                continue

            field_name = item.target.id
            if field_name.startswith("_"):
                continue

            # Get type hint as string
            try:
                type_hint = ast.unparse(item.annotation)
            except Exception:
                type_hint = "unknown"

            # Get default value
            default = None
            if item.value is not None:
                try:
                    default = ast.unparse(item.value)
                except Exception:
                    default = "..."

            # Convert field_name to ENV_VAR_NAME (upper snake)
            env_name = field_name.upper()

            env_vars.append(
                EnvVar(
                    name=field_name,
                    env_name=env_name,
                    type_hint=type_hint,
                    default=default,
                    description=None,
                )
            )

    return env_vars
