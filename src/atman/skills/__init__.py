"""
atman.skills — optional skill-loop for Atman agents.

Public surface:
  SkillManagerPort  — abstract interface used everywhere outside this package
  NoopSkillManager  — drop-in when skills.enabled = false
  SkillManager      — real implementation (requires Postgres + embedding)
  SkillsDisabledError

All other internals (store, retriever, projection, manifest) are package-private.
Disable the entire loop by setting atman.skills.enabled = false in config —
nothing outside this package needs to change.
"""

from atman.skills.models import (
    Skill,
    SkillInvocation,
    SkillKind,
    SkillOrigin,
    SkillStatus,
    SkillSuggestion,
)
from atman.skills.noop import NoopSkillManager, SkillsDisabledError
from atman.skills.port import SkillManagerPort

__all__ = [
    "Skill",
    "SkillInvocation",
    "SkillKind",
    "SkillOrigin",
    "SkillStatus",
    "SkillSuggestion",
    "SkillManagerPort",
    "NoopSkillManager",
    "SkillsDisabledError",
]
