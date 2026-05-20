"""ProjectionAdapter — registers/unregisters skills as tools in agent session pool.

MVP: PydanticAgentProjector is a no-op because pydantic-ai tools are registered
via make_skill_tools() at session start rather than via filesystem projection.

The Protocol is the extension point for future runtimes (OpenClaw, Claude Code, Cursor)
that need skills projected as files into an agent workspace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from atman.skills.models import Skill


@runtime_checkable
class ProjectionAdapter(Protocol):
    def project_skill(self, skill: Skill, agent_workspace: Path) -> None:
        """Make a skill available in the agent's active session."""
        ...

    def unproject_skill(self, skill: Skill, agent_workspace: Path) -> None:
        """Remove a skill from the agent's active session."""
        ...

    def list_projected(self, agent_workspace: Path) -> list[str]:
        """Return names of skills currently projected in the workspace."""
        ...


class PydanticAgentProjector:
    """MVP projector for pydantic-ai agents.

    Skills are registered as tools via make_skill_tools() at session bootstrap,
    not via filesystem projection. This projector is a no-op placeholder;
    the real registration happens in the agent runner.
    """

    def project_skill(self, skill: Skill, agent_workspace: Path) -> None:
        # MVP: pydantic-ai registers tools from code, not from filesystem projection.
        del skill, agent_workspace

    def unproject_skill(self, skill: Skill, agent_workspace: Path) -> None:
        del skill, agent_workspace

    def list_projected(self, agent_workspace: Path) -> list[str]:
        del agent_workspace
        return []
