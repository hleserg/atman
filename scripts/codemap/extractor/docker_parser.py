"""Parse docker-compose.yml for service information."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def parse_services(compose_path: Path) -> dict[str, dict]:
    """Return dict of service_name -> service_config from docker-compose.yml."""
    if not compose_path.exists():
        return {}
    try:
        import yaml  # pyyaml is a project dep
    except ImportError:
        log.warning("pyyaml not available; docker_parser returning empty services")
        return {}

    try:
        with compose_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        log.warning("Failed to parse %s: %s", compose_path, exc)
        return {}

    if not isinstance(data, dict):
        return {}
    return data.get("services", {}) or {}
