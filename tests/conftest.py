"""
Shared pytest fixtures and configuration for the Atman test suite.
"""

import httpx
import pytest


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    """Probe Ollama API; return True if reachable, False otherwise."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-skip tests marked ``requires_ollama`` when Ollama is unreachable."""
    skip_marker = pytest.mark.skip(reason="Ollama is not reachable at localhost:11434")

    ollama_ok: bool | None = None

    for item in items:
        if "requires_ollama" not in item.keywords:
            continue

        if ollama_ok is None:
            try:
                resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
                ollama_ok = resp.status_code == 200
            except (httpx.ConnectError, httpx.TimeoutException):
                ollama_ok = False

        if not ollama_ok:
            item.add_marker(skip_marker)
