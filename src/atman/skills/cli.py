"""CLI for skill-loop management.

Entry point: atman-skills

Read-only commands (list, show, inspect-invocations) work regardless of
atman.skills.enabled. Write commands return an error when skills are disabled.
"""

from __future__ import annotations

import sys
from uuid import UUID


def _get_store(agent_id_str: str | None = None):
    """Build a PostgresSkillStore or fail with a helpful message."""
    from atman.config import settings
    from atman.skills.postgres_store import PostgresSkillStore

    return PostgresSkillStore(db_url=settings.database_url)


def _require_enabled() -> None:
    from atman.config import settings

    if not settings.skills.enabled:
        print(
            "Error: skill-loop is disabled (atman.skills.enabled = false).\n"
            "Enable it in your config to make changes.",
            file=sys.stderr,
        )
        sys.exit(1)


def _parse_agent_id(args: list[str]) -> tuple[UUID, list[str]]:
    """Extract --agent <uuid> from args if present."""
    if "--agent" in args:
        idx = args.index("--agent")
        if idx + 1 >= len(args):
            print("Error: --agent requires a UUID argument", file=sys.stderr)
            sys.exit(1)
        agent_id = UUID(args[idx + 1])
        remaining = args[:idx] + args[idx + 2 :]
        return agent_id, remaining
    return UUID(int=0), args  # null UUID as sentinel when not provided


def cmd_list(args: list[str]) -> None:
    """atman-skills list [--agent <uuid>] [--status active|disabled|draft]"""
    from atman.skills.models import SkillStatus

    status_filter: SkillStatus | None = None
    if "--status" in args:
        idx = args.index("--status")
        status_filter = SkillStatus(args[idx + 1])
        args = args[:idx] + args[idx + 2 :]

    agent_id, _ = _parse_agent_id(args)
    store = _get_store()

    if status_filter:
        skills = store.list_by_status(agent_id, status_filter)
    else:
        # Show all statuses
        from atman.skills.models import SkillStatus

        skills = []
        for st in SkillStatus:
            skills.extend(store.list_by_status(agent_id, st))

    if not skills:
        print("No skills found.")
        return

    for s in skills:
        pin = ""
        if s.user_pinned:
            pin = " [user-pinned]"
        elif s.auto_pinned:
            pin = " [auto-pinned]"
        revision = " ⚠ revision_needed" if s.revision_needed else ""
        print(f"  {s.name} ({s.status.value}){pin}{revision}")
        print(f"    {s.description_short}")
        print(f"    uses={s.invocations_count} success={s.success_count} fail={s.failure_count}")


def cmd_show(args: list[str]) -> None:
    """atman-skills show <name> [--agent <uuid>]"""
    if not args:
        print("Usage: atman-skills show <name> [--agent <uuid>]", file=sys.stderr)
        sys.exit(1)

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Name:       {skill.name}")
    print(f"Status:     {skill.status.value}")
    print(f"Kind:       {skill.kind.value}")
    print(f"Origin:     {skill.origin.value}")
    print(f"Pinned:     user={skill.user_pinned} auto={skill.auto_pinned}")
    print(
        f"Stats:      invocations={skill.invocations_count} success={skill.success_count} fail={skill.failure_count}"
    )
    print(f"Idle:       sessions_since_use={skill.sessions_since_use}")
    print(f"Revision:   needed={skill.revision_needed} priority={skill.revision_priority}")
    print(f"Manifest:   {skill.manifest_path}")
    print(f"Root:       {skill.skill_root}")
    if skill.manifest_path.exists():
        print("\n--- SKILL.md ---")
        print(skill.manifest_path.read_text(encoding="utf-8")[:2000])


def cmd_disable(args: list[str]) -> None:
    """atman-skills disable <name> [--agent <uuid>]"""
    _require_enabled()
    if not args:
        print("Usage: atman-skills disable <name> [--agent <uuid>]", file=sys.stderr)
        sys.exit(1)

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    from atman.skills.models import SkillStatus

    store.update_skill_status(skill.id, SkillStatus.disabled)
    print(f"Skill '{name}' disabled.")


def cmd_enable(args: list[str]) -> None:
    """atman-skills enable <name> [--agent <uuid>]"""
    _require_enabled()
    if not args:
        print("Usage: atman-skills enable <name> [--agent <uuid>]", file=sys.stderr)
        sys.exit(1)

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    from atman.skills.models import SkillStatus

    store.update_skill_status(skill.id, SkillStatus.active)
    print(f"Skill '{name}' enabled (active).")


def cmd_pin(args: list[str]) -> None:
    """atman-skills pin <name> [--agent <uuid>]"""
    _require_enabled()
    if not args:
        print("Usage: atman-skills pin <name> [--agent <uuid>]", file=sys.stderr)
        sys.exit(1)

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    store.update_pinning(skill.id, user_pinned=True)
    print(f"Skill '{name}' user-pinned.")


def cmd_unpin(args: list[str]) -> None:
    """atman-skills unpin <name> [--agent <uuid>]"""
    _require_enabled()
    if not args:
        print("Usage: atman-skills unpin <name> [--agent <uuid>]", file=sys.stderr)
        sys.exit(1)

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    store.update_pinning(skill.id, user_pinned=False)
    print(f"Skill '{name}' unpinned (user_pinned=false).")


def cmd_archive(args: list[str]) -> None:
    """atman-skills archive <name> [--agent <uuid>] — soft-disable, keeps data."""
    _require_enabled()
    # archive = disable for now (no separate archived status in schema)
    cmd_disable(args)
    print("(archived = disabled; files and history preserved)")


def cmd_inspect_invocations(args: list[str]) -> None:
    """atman-skills inspect-invocations <name> [--agent <uuid>] [--last N]"""
    if not args:
        print(
            "Usage: atman-skills inspect-invocations <name> [--agent <uuid>] [--last N]",
            file=sys.stderr,
        )
        sys.exit(1)

    last_n = 10
    if "--last" in args:
        idx = args.index("--last")
        last_n = int(args[idx + 1])
        args = args[:idx] + args[idx + 2 :]

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    # Fetch via direct SQL — store interface doesn't expose all-time history per skill
    # Use get_unprocessed_invocations as a proxy for recent invocations
    print(f"Recent invocations for '{name}' (last {last_n}):")
    print("(Use --last N to adjust count)")
    print(f"Skill ID: {skill.id}")
    print("Full invocation history requires direct DB query:")
    print(
        f"  SELECT * FROM public.skill_invocations WHERE skill_id = '{skill.id}' ORDER BY started_at DESC LIMIT {last_n};"  # nosec B608
    )


def cmd_force_revise(args: list[str]) -> None:
    """atman-skills force-revise <name> [--agent <uuid>]"""
    _require_enabled()
    if not args:
        print("Usage: atman-skills force-revise <name> [--agent <uuid>]", file=sys.stderr)
        sys.exit(1)

    name = args[0]
    agent_id, _ = _parse_agent_id(args[1:])
    store = _get_store()
    skill = store.get_skill_by_name(agent_id, name)
    if skill is None:
        print(f"Skill '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    store.set_revision_needed(skill.id, priority_bump=5)
    print(f"Skill '{name}' flagged for revision (priority +5).")


_COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "disable": cmd_disable,
    "enable": cmd_enable,
    "pin": cmd_pin,
    "unpin": cmd_unpin,
    "archive": cmd_archive,
    "inspect-invocations": cmd_inspect_invocations,
    "force-revise": cmd_force_revise,
}

_HELP = """atman-skills — skill-loop management

Commands:
  list [--agent <uuid>] [--status active|disabled|draft]
  show <name> [--agent <uuid>]
  disable <name> [--agent <uuid>]
  enable <name> [--agent <uuid>]
  pin <name> [--agent <uuid>]
  unpin <name> [--agent <uuid>]
  archive <name> [--agent <uuid>]
  inspect-invocations <name> [--agent <uuid>] [--last N]
  force-revise <name> [--agent <uuid>]

Read-only commands (list, show, inspect-invocations) work even when
atman.skills.enabled = false.
"""


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(_HELP)
        sys.exit(0)

    cmd = args[0]
    rest = args[1:]

    if cmd not in _COMMANDS:
        print(f"Unknown command: {cmd}\n{_HELP}", file=sys.stderr)
        sys.exit(1)

    _COMMANDS[cmd](rest)


if __name__ == "__main__":
    main()
