#!/usr/bin/env python3
"""
Запуск Atman агента.

    uv run src/run_agent.py                      # создать нового агента
    uv run src/run_agent.py --agent 1            # запустить агента #1
    uv run src/run_agent.py --new "Мой агент"    # создать с описанием
    uv run src/run_agent.py --list               # список агентов
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

_DEFAULT_WORKSPACE_ROOT = Path("~/.atman/agents")
_DEFAULT_MODEL = "ollama:qwen3.5:9b"


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k in env or not env})
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Atman agent REPL")
    parser.add_argument("--agent", type=int, metavar="ID",
                        help="Числовой ID агента")
    parser.add_argument("--new", metavar="DESCRIPTION", nargs="?", const="",
                        help="Создать нового агента")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    parser.add_argument("--workspace-root", type=Path, default=_DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    env = _load_env()
    app_url = env.get("DATABASE_URL")
    admin_url = env.get("ATMAN_ADMIN_DATABASE_URL") or app_url

    if not app_url:
        raise SystemExit("DATABASE_URL не найден. Проверь .env")

    from atman.agents_registry import AgentsRegistry
    registry = AgentsRegistry(app_url=app_url, admin_url=admin_url)

    if args.list:
        agents = registry.list_all()
        if not agents:
            print("Агентов нет. Создай: uv run src/run_agent.py --new 'Имя'")
            return
        print(f"{'#':<5} {'UUID':<38} Описание")
        print("-" * 70)
        for a in agents:
            print(f"{a.serial_id:<5} {str(a.uuid):<38} {a.description or a.name or '—'}")
        return

    if args.new is not None:
        record = registry.create(description=args.new, name=args.new or "agent")
        print(f"Создан агент #{record.serial_id}  {record.uuid}")
        if args.new:
            print(f"  {args.new}")
    elif args.agent is not None:
        record = registry.get_by_serial(args.agent)
        if record is None:
            raise SystemExit(f"Агент #{args.agent} не найден. Список: --list")
    else:
        record = registry.create(description="", name="agent")
        print(f"Новый агент #{record.serial_id}. Повторный запуск: --agent {record.serial_id}")

    workspace = args.workspace_root.expanduser() / str(record.serial_id)
    desc = record.description or record.name or ""
    if desc:
        print(f"Агент #{record.serial_id}: {desc}")
    print(f"UUID: {record.uuid}\n")

    from atman.adapters.agent.config import AgentConfig, ModelConfig
    from atman.adapters.agent.runner import AtmanRunner

    config = AgentConfig(model=ModelConfig(model=args.model))
    runner = AtmanRunner(workspace=workspace, agent_id=record.uuid, config=config)

    try:
        asyncio.run(runner.chat())
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
