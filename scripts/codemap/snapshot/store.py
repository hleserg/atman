"""Snapshot store — persist component AST inventory to .codemap/snapshots/."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SNAPSHOTS_DIR = Path(".codemap/snapshots")


@dataclass
class ComponentSnapshot:
    component_id: str
    recorded_at: str  # ISO 8601
    class_names: list[str] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    port_names: list[str] = field(default_factory=list)
    pydantic_model_names: list[str] = field(default_factory=list)
    cli_commands: list[str] = field(default_factory=list)
    todo_count: int = 0
    file_count: int = 0
    schema_versions: list[str] = field(default_factory=list)


def _snapshot_path(component_id: str, base: Path) -> Path:
    safe = component_id.replace("/", "_").replace(".", "_")
    return base / f"{safe}.json"


def load_snapshot(component_id: str, base: Path = SNAPSHOTS_DIR) -> ComponentSnapshot | None:
    path = _snapshot_path(component_id, base)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ComponentSnapshot(**data)
    except Exception as exc:
        log.warning("Failed to load snapshot %s: %s", path, exc)
        return None


def save_snapshot(snapshot: ComponentSnapshot, base: Path = SNAPSHOTS_DIR) -> None:
    base.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(snapshot.component_id, base)
    try:
        path.write_text(json.dumps(asdict(snapshot), indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("Failed to save snapshot %s: %s", path, exc)


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
