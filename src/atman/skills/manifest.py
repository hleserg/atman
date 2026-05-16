"""SKILL.md manifest parsing and writing.

Format: YAML frontmatter (between --- delimiters) + markdown body.
The YAML frontmatter follows the Agent Skills Open Standard.
Atman-specific fields live in metadata.atman namespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from atman.skills.models import SkillKind, SkillOrigin


@dataclass
class SkillManifest:
    name: str
    description: str
    version: str = "0.1.0"
    kind: SkillKind = SkillKind.active
    origin: SkillOrigin = SkillOrigin.in_session
    core: bool = False
    session_scoped: bool = False
    triggers_keywords: list[str] = field(default_factory=list)
    triggers_embedding_anchors: list[str] = field(default_factory=list)
    min_confidence: float = 0.65
    dependencies_skills: list[str] = field(default_factory=list)
    dependencies_python_packages: list[str] = field(default_factory=list)
    runtime_entry: str | None = None
    runtime_sandbox: str = "none"  # subprocess|inline|none
    manifest_inferred: bool = False
    body: str = ""  # markdown body (after frontmatter)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def parse_skill_md(path: Path) -> SkillManifest:
    """Parse a SKILL.md file and return a SkillManifest.

    Raises:
        ValueError: if the file has no valid YAML frontmatter or missing name/description.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"No valid YAML frontmatter in {path}")

    raw_yaml, body = match.group(1), match.group(2)
    data = yaml.safe_load(raw_yaml) or {}

    name = data.get("name")
    description = data.get("description", "")
    if not name:
        raise ValueError(f"SKILL.md at {path} missing required field 'name'")

    meta = data.get("metadata", {}) or {}
    atman = meta.get("atman", {}) or {}
    triggers = atman.get("triggers", {}) or {}
    deps = atman.get("dependencies", {}) or {}
    runtime = atman.get("runtime", {}) or {}

    return SkillManifest(
        name=str(name),
        description=str(description).strip(),
        version=str(meta.get("version", "0.1.0")),
        kind=SkillKind(atman.get("kind", "active")),
        origin=SkillOrigin(atman.get("origin", "in_session")),
        core=bool(atman.get("core", False)),
        session_scoped=bool(atman.get("session_scoped", False)),
        triggers_keywords=list(triggers.get("keywords", [])),
        triggers_embedding_anchors=list(triggers.get("embedding_anchors", [])),
        min_confidence=float(triggers.get("min_confidence", 0.65)),
        dependencies_skills=list(deps.get("skills", [])),
        dependencies_python_packages=list(deps.get("python_packages", [])),
        runtime_entry=runtime.get("entry"),
        runtime_sandbox=str(runtime.get("sandbox", "none")),
        manifest_inferred=bool(atman.get("manifest_inferred", False)),
        body=body.strip(),
    )


def write_skill_md(manifest: SkillManifest, path: Path) -> None:
    """Write a SkillManifest as a SKILL.md file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    atman_block: dict = {
        "origin": manifest.origin.value,
        "kind": manifest.kind.value,
        "core": manifest.core,
        "session_scoped": manifest.session_scoped,
    }
    if manifest.triggers_keywords or manifest.triggers_embedding_anchors:
        atman_block["triggers"] = {
            "keywords": manifest.triggers_keywords,
            "embedding_anchors": manifest.triggers_embedding_anchors,
            "min_confidence": manifest.min_confidence,
        }
    if manifest.dependencies_skills or manifest.dependencies_python_packages:
        atman_block["dependencies"] = {
            "skills": manifest.dependencies_skills,
            "python_packages": manifest.dependencies_python_packages,
        }
    if manifest.runtime_entry:
        atman_block["runtime"] = {
            "entry": manifest.runtime_entry,
            "sandbox": manifest.runtime_sandbox,
        }
    if manifest.manifest_inferred:
        atman_block["manifest_inferred"] = True

    frontmatter = {
        "name": manifest.name,
        "description": manifest.description,
        "metadata": {
            "author": "atman-agent",
            "version": manifest.version,
            "atman": atman_block,
        },
    }

    yaml_text = yaml.dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    body = manifest.body or f"# {manifest.name}\n\n{manifest.description}\n"
    path.write_text(f"---\n{yaml_text}---\n\n{body}\n", encoding="utf-8")
