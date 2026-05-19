"""Re-export shim: SkillManagerPort has moved to atman.core.ports.skill_manager.

Import from the canonical location instead:
    from atman.core.ports.skill_manager import SkillManagerPort
"""

import warnings

from atman.core.ports.skill_manager import SkillManagerPort

warnings.warn(
    "atman.skills.port is deprecated; import SkillManagerPort from "
    "atman.core.ports.skill_manager instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["SkillManagerPort"]
