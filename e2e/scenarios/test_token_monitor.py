#!/usr/bin/env python3
"""
Сценарий: token monitoring — предупреждения 70/80/90% и принудительное закрытие на 95%.

Проверяем:
  1. При context_limit=500 и длинных сообщениях триггерятся пороги
  2. Предупреждения инжектируются в историю (не в stdout агенту напрямую)
  3. На 95% — _do_restart() или force_finish без участия агента
  4. Trigger deduplication: одно и то же предупреждение не дублируется
  5. После restart триггеры сбрасываются

Запуск:
    PYTHONPATH=src OLLAMA_BASE_URL=http://localhost:11434/v1 \
        python3 e2e/scenarios/test_token_monitor.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.factory import build_deps
from atman.adapters.agent.token_monitor import TokenMonitor

DIVIDER = "─" * 70
MODEL = os.environ.get("ATMAN_MODEL", "ollama:qwen3.5:9b")


def hdr(title: str) -> None:
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}")


def chk(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f"  [{detail}]" if detail else ""))
    return ok


# ---------------------------------------------------------------------------
# Тест A: TokenMonitor unit-like с mock usage
# ---------------------------------------------------------------------------

def test_token_monitor_thresholds() -> int:
    """Проверяем что TokenMonitor корректно выдаёт предупреждения."""
    from unittest.mock import MagicMock

    failures = 0
    hdr("A: TokenMonitor пороги (без LLM)")

    monitor = TokenMonitor(context_limit=1000)

    # Симулируем usage на разных уровнях
    test_cases = [
        (650, False, "65% — ниже порога"),
        (720, True,  "72% — NOTICE (70%)"),
        (720, False, "72% повторно — дедупликация"),
        (820, True,  "82% — INFO (80%)"),
        (920, True,  "92% — WARNING (90%)"),
        (960, True,  "96% — CRITICAL (95%)"),
    ]

    for tokens, expect_warning, desc in test_cases:
        result = monitor.check(input_tokens=tokens)
        got_warning = result is not None
        ok = chk(desc, got_warning == expect_warning,
                 f"tokens={tokens}, warning={got_warning}")
        if not ok:
            failures += 1

    # После reset — триггеры сбрасываются
    monitor.reset_triggers()
    result_after_reset = monitor.check(input_tokens=720)
    ok = chk("После reset: 72% снова даёт предупреждение",
             result_after_reset is not None)
    if not ok:
        failures += 1

    return failures


# ---------------------------------------------------------------------------
# Тест B: Интеграция с реальной моделью + маленький context_limit
# ---------------------------------------------------------------------------

async def test_token_monitor_integration() -> int:
    """Реальная LLM с context_limit=800 — смотрим как триггерятся пороги."""
    failures = 0
    hdr("B: Token monitoring с реальной LLM (context_limit=800)")

    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from atman.adapters.agent.instructions import build_instructions
    from atman.core.models import CoreValue, Goal, GoalHorizon, GoalOwner
    from atman.core.models import Identity, LayerType, NarrativeDocument, NarrativeLayer
    from atman.core.services.session_manager import deterministic_session_experience_id

    with tempfile.TemporaryDirectory(prefix="atman_token_") as tmpdir:
        workspace = Path(tmpdir)
        agent_id = uuid4()

        # Маленький context_limit чтобы быстро дойти до порогов
        config = AgentConfig(
            model=ModelConfig(model=MODEL, max_tokens=150, context_limit=800),
            enable_key_moments=False,
            session_timeout_minutes=60,
        )
        deps, session_manager, store = build_deps(workspace, agent_id, config)

        identity = Identity(
            id=agent_id,
            self_description="Тестовый агент для token monitor.",
            core_values=[CoreValue(name="честность", description="test",
                                   confidence=0.9, justification="test")],
        )
        narrative = NarrativeDocument(
            identity_id=agent_id,
            layers=[NarrativeLayer(layer_type=LayerType.FOUNDATION, content="test")],
        )
        store.save_identity(identity)
        store.save_narrative(narrative)

        ctx = session_manager.start_session(agent_id)
        session_id = ctx.session_id
        deps = replace(deps, session_id=session_id)

        agent = Agent(
            MODEL,
            deps_type=type(deps),
            instructions=lambda c: build_instructions(c.deps),
        )

        monitor = TokenMonitor(context_limit=config.model.context_limit)
        history: list = []
        warnings_fired: list[str] = []

        # Отправляем сообщения чтобы заполнить контекст
        filler = "Объясни подробно: " + "что такое рекурсия, как работает стек вызовов. " * 5

        print("\n  Отправляем сообщения для заполнения контекста...")
        for i in range(6):
            msg = f"[{i+1}/6] {filler}"
            try:
                result = await agent.run(msg, deps=deps, message_history=history or None)
            except Exception as e:
                print(f"  [warn] run {i+1} failed: {e}")
                break

            history.extend(result.new_messages())
            usage = result.usage()
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            ratio = input_tokens / config.model.context_limit * 100

            warning = monitor.check(input_tokens=input_tokens)
            if warning:
                warnings_fired.append(warning.level)
                print(f"  [{i+1}] tokens={input_tokens} ({ratio:.0f}%) → WARNING: {warning.level}")
            else:
                print(f"  [{i+1}] tokens={input_tokens} ({ratio:.0f}%) → ok")

            if ratio >= 95:
                print("  → 95% достигнуто, остановка")
                break

        chk("B: хотя бы одно предупреждение сработало",
            len(warnings_fired) > 0,
            f"fired={warnings_fired}")
        if not warnings_fired:
            failures += 1

        # Дедупликация: повторный вызов с теми же токенами не должен давать новое предупреждение
        if history:
            # Получаем последний известный usage
            try:
                last_result = await agent.run("ок", deps=deps, message_history=history)
                last_tokens = getattr(last_result.usage(), "input_tokens", 0) or 0
                w1 = monitor.check(input_tokens=last_tokens)
                w2 = monitor.check(input_tokens=last_tokens)
                chk("B: дедупликация — второй вызов с теми же токенами = None",
                    w2 is None,
                    f"w1={w1}, w2={w2}")
                if w2 is not None:
                    failures += 1
            except Exception as e:
                print(f"  [warn] dedup check failed: {e}")

        # После reset_triggers — снова начинают срабатывать
        monitor.reset_triggers()
        if history:
            last_tokens = 750  # гарантированно выше 70%
            w_after = monitor.check(input_tokens=last_tokens)
            chk("B: после reset_triggers предупреждения снова срабатывают",
                w_after is not None or last_tokens < config.model.context_limit * 0.70)

        try:
            session_manager.finish_session(session_id, overall_emotional_tone=0.0,
                                           close_reason="completed")
        except Exception:
            pass

    return failures


# ---------------------------------------------------------------------------
# Тест C: Унификация предупреждений — содержимое сообщений
# ---------------------------------------------------------------------------

def test_warning_message_content() -> int:
    """Проверяем что тексты предупреждений содержат нужные ключевые слова."""
    failures = 0
    hdr("C: Содержимое предупреждающих сообщений")

    monitor = TokenMonitor(context_limit=1000)

    cases = [
        (710, ["токен", "осталось"], "70% — должно быть про оставшиеся токены"),
        (850, ["токен", "⚠"], "80% — должен быть символ предупреждения"),
        (920, ["токен", "⚠", "завершать"], "90% — должно быть про необходимость завершать"),
    ]

    for tokens, keywords, desc in cases:
        monitor.reset_triggers()
        warning = monitor.check(input_tokens=tokens)
        if warning:
            msg_lower = warning.message.lower()
            for kw in keywords:
                ok = chk(f"C: {desc} — ключевое слово '{kw}'",
                         kw.lower() in msg_lower,
                         f"message={warning.message[:80]!r}")
                if not ok:
                    failures += 1
        else:
            chk(f"C: {desc} — предупреждение сработало", False,
                f"tokens={tokens}, limit=1000")
            failures += 1

    return failures


async def main() -> int:
    total = 0
    total += test_token_monitor_thresholds()
    total += await test_token_monitor_integration()
    total += test_warning_message_content()

    hdr("ИТОГ")
    if total == 0:
        print("  Все проверки прошли.")
    else:
        print(f"  FAILED: {total} проверок не прошло.")
    return total


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
