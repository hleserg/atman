"""
Atman Agent Adapter - Pydantic AI integration layer.

This adapter connects SessionManager, IdentityStore, and ReflectionEngine
to a real LLM via Pydantic AI. It provides:

1. AtmanDeps - typed dependency container
2. AtmanAgent - Pydantic AI Agent with dynamic instructions from identity
3. Agent tools for recording and querying experience
4. Session lifecycle hooks for experience transfer and reflection
5. AgentRunner - execution layer with token monitoring (E22.3)
"""

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.deps import AtmanDeps
from atman.adapters.agent.instructions import build_instructions
from atman.adapters.agent.runner import AgentRunner, ContextLimitExceeded
from atman.adapters.agent.tools import log_experience, record_key_moment

__all__ = [
    "AgentConfig",
    "AgentRunner",
    "AtmanDeps",
    "ContextLimitExceeded",
    "ModelConfig",
    "build_instructions",
    "log_experience",
    "record_key_moment",
]
