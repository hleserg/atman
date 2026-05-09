"""SYSTEM_MAP §5.1 regression tests for deployment script safety."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENWEBUI_SETUP = REPO_ROOT / "setup-openwebui.sh"


def _openwebui_setup_text() -> str:
    return OPENWEBUI_SETUP.read_text(encoding="utf-8")


def test_openwebui_defaults_to_localhost_only() -> None:
    """Open WebUI must not expose the first-admin registration flow to LAN by default."""
    script = _openwebui_setup_text()

    assert "ATMAN_OPENWEBUI_ENABLE_LAN:-0" in script
    assert 'OPENWEBUI_BIND_ADDRESS="127.0.0.1"' in script
    assert '- "${OPENWEBUI_BIND_ADDRESS}:${OPENWEBUI_PORT}:8080"' in script
    assert '- "0.0.0.0:${OPENWEBUI_PORT}:8080"' not in script


def test_openwebui_windows_portproxy_requires_lan_opt_in() -> None:
    """Windows portproxy/firewall changes must be gated by explicit LAN opt-in."""
    script = _openwebui_setup_text()
    auto_portproxy_block = script[
        script.index("# 9. Пробуем запустить netsh прямо сейчас через cmd.exe") : script.index(
            "# 10. Скрипт автообновления IP при перезапуске WSL"
        )
    ]

    assert "if $LAN_ACCESS; then" in auto_portproxy_block
    assert "netsh interface portproxy add" in auto_portproxy_block
    assert "ATMAN_OPENWEBUI_ENABLE_LAN=1" in auto_portproxy_block


def test_openwebui_refresh_portproxy_refuses_default_lan() -> None:
    """The generated refresh helper must keep the safe default after WSL restarts."""
    script = _openwebui_setup_text()

    assert 'case "${ATMAN_OPENWEBUI_ENABLE_LAN:-0}" in' in script
    assert "LAN-проброс отключён по умолчанию" in script
    assert "ATMAN_OPENWEBUI_ENABLE_LAN=1 $0" in script
