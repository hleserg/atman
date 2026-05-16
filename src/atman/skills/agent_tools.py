"""Pydantic-ai tool definitions for the skill-loop.

Call make_skill_tools() to get the list of tool functions to register
with the agent. Returns an empty list when skill_manager is None (disabled).

The four tools implement the agent ↔ Atman skill contract:
  atman_skills_list_available  — what skills are on hand
  atman_skills_invoke          — start using a skill
  atman_skills_mark_result     — explicit feedback (helped/didnt_help/unclear)
  atman_skills_capture         — save a new skill discovered in-session
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from atman.skills.port import SkillManagerPort

_log = logging.getLogger(__name__)


def make_skill_tools(
    skill_manager: SkillManagerPort | None,
    agent_id: UUID,
    session_id: UUID,
) -> list:
    """Return pydantic-ai tool functions for skill interaction.

    Returns an empty list when skill_manager is None so callers don't
    need to guard — the tools simply don't exist in the session.
    """
    if skill_manager is None:
        return []

    def atman_skills_list_available() -> str:
        """List skills currently available in this session (pinned + on-demand loaded)."""
        try:
            skills = skill_manager.list_available(agent_id, session_id)
            if not skills:
                return "No skills available in this session."
            lines = ["Available skills:\n"]
            for s in skills:
                pin_marker = " [pinned]" if s.is_pinned else ""
                lines.append(f"- {s.name}{pin_marker}: {s.description_short}\n")
            return "".join(lines)
        except Exception as exc:
            _log.warning("atman_skills_list_available error: %s", exc)
            return f"Error listing skills: {exc}"

    def atman_skills_invoke(skill_name: str, args: str = "{}") -> str:
        """Invoke a skill by name.

        Args:
            skill_name: kebab-case skill name (e.g. 'smart-outlet-control')
            args: JSON-encoded arguments dict passed to the skill entry script

        Returns:
            invocation_id to use with atman_skills_mark_result, plus execution status.
        """
        try:
            skill = skill_manager.get_skill(agent_id, skill_name)
            if skill is None:
                return f"Skill '{skill_name}' not found or not available."
            parsed_args: dict = {}
            if args.strip():
                try:
                    parsed_args = json.loads(args)
                except json.JSONDecodeError:
                    parsed_args = {"raw": args}
            invocation_id = skill_manager.invoke(skill.id, parsed_args, agent_id, session_id)
            return (
                f"Skill '{skill_name}' invoked. invocation_id={invocation_id}\n"
                "After you see the result, call atman_skills_mark_result with your verdict."
            )
        except Exception as exc:
            _log.warning("atman_skills_invoke error: %s", exc)
            return f"Error invoking skill '{skill_name}': {exc}"

    def atman_skills_mark_result(
        invocation_id: str,
        status: str,
        note: str = "",
    ) -> str:
        """Record the outcome of a skill invocation.

        Args:
            invocation_id: UUID returned by atman_skills_invoke
            status: one of 'helped', 'didnt_help', 'unclear'
            note: optional human-readable note about the outcome

        This is your note to your future self. Without it, micro reflection
        uses heuristics and may get the verdict wrong.
        """
        valid = {"helped", "didnt_help", "unclear"}
        if status not in valid:
            return f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid))}"
        try:
            skill_manager.mark_result(
                UUID(invocation_id),
                status,
                note if note.strip() else None,
            )
            return f"Result recorded: {status}" + (f" — {note}" if note.strip() else "")
        except Exception as exc:
            _log.warning("atman_skills_mark_result error: %s", exc)
            return f"Error recording result: {exc}"

    def atman_skills_capture(
        name: str,
        description: str,
        instructions: str = "",
    ) -> str:
        """Save a new skill you just figured out in this session.

        Use this when you've developed a reusable approach and want to remember
        it for future sessions. The skill is created as a draft and will be
        promoted to active after successful use.

        Args:
            name: kebab-case skill name (e.g. 'parse-invoice-csv')
            description: one-paragraph description of what this skill does and when to use it
            instructions: step-by-step usage instructions (markdown ok)
        """
        try:
            skill = skill_manager.capture(
                name=name,
                description=description,
                agent_id=agent_id,
                session_id=session_id,
                instructions=instructions if instructions.strip() else None,
            )
            return (
                f"Skill '{skill.name}' captured (status=draft). "
                f"It will become active after successful use. "
                f"Manifest: {skill.manifest_path}"
            )
        except Exception as exc:
            _log.warning("atman_skills_capture error: %s", exc)
            return f"Error capturing skill '{name}': {exc}"

    return [
        atman_skills_list_available,
        atman_skills_invoke,
        atman_skills_mark_result,
        atman_skills_capture,
    ]
