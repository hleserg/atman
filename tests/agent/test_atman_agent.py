"""
Smoke tests for Pydantic AI test agent.

These tests verify that the agent can be created and interact with its LLM.
They are SKIPPED unless the agent's LLM endpoint (default: Gemma4 at :8080) is available.
"""

import os
import tomllib
from pathlib import Path

import pytest

from agent.atman_agent import create_agent
from agent.config import AgentLLMConfig

_TEST_AGENT_KEY_ENV = "ATMAN_TEST_AGENT_API_KEY"


def test_agent_can_be_constructed_without_llm_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory wiring should not fail before the first model request."""
    monkeypatch.setenv(_TEST_AGENT_KEY_ENV, "unit-test-not-a-secret")
    config = AgentLLMConfig(
        base_url="http://127.0.0.1:9/v1",
        model="gemma4",
        api_key=os.environ[_TEST_AGENT_KEY_ENV],
    )

    agent = create_agent(config)

    assert agent is not None


def test_agent_package_is_included_in_wheel() -> None:
    """The documented top-level agent package must ship in built wheels."""
    pyproject = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())

    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]

    assert "agent" in packages


@pytest.mark.requires_agent_llm
def test_agent_responds():
    """Test that agent can respond to a simple prompt."""
    agent = create_agent()
    result = agent.run_sync("Say hello.")
    assert result.output
    assert isinstance(result.output, str)


@pytest.mark.requires_agent_llm
def test_agent_with_custom_config():
    """Test that agent respects custom configuration."""
    config = AgentLLMConfig(
        base_url="http://localhost:8080/v1",
        model="gemma4",
        api_key="custom-key",
    )
    agent = create_agent(config)
    # Just verify the agent is created successfully
    assert agent is not None
