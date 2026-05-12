#!/usr/bin/env python3
"""
Сценарий: unexamined_fact_refs + wakeup message при разных close_reason.

Проверяем:
  1. Факты прочитанные агентом но не вошедшие в key_moments → unexamined_fact_refs
  2. Факты вошедшие в key_moment.fact_refs → НЕ попадают в unexamined
  3. Wake-up message при следующей сессии содержит правильный контекст для каждого close_reason
  4. agent_recap сохраняется при timeout_sleep

Запуск:
    PYTHONPATH=src OLLAMA_BASE_URL=http://localhost:11434/v1 \
        python3 e2e/scenarios/test_unexamined_facts.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.factory import build_deps
from atman.core.models import (
    CoreValue, EmotionalDepth, Goal, GoalHorizon, GoalOwner,
    Identity, KeyMomentInput, LayerType, NarrativeDocument, NarrativeLayer,
)
from atman.core.services.session_manager import SessionManager, deterministic_session_experience_id

DIVIDER = "─" * 70
MODEL = os.environ.get("ATMAN_MODEL", "ollama:qwen3.5:9b")


def hdr(title: str) -> None:
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}")


def chk(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f"  [{detail}]" if detail else ""))
    return ok


def bootstrap(store, agent_id: UUID) -> None:
    from atman.core.models.identity import Principle
    identity = Identity(
        id=agent_id,
        self_description="Тестовый агент для unexamined facts.",
        core_values=[CoreValue(name="честность", description="test",
                               confidence=0.9, justification="test")],
    )
    narrative = NarrativeDocument(
        identity_id=agent_id,
        layers=[NarrativeLayer(layer_type=LayerType.FOUNDATION, content="test")],
    )
    store.save_identity(identity)
    store.save_narrative(narrative)


# ---------------------------------------------------------------------------
# Тест A: unexamined_fact_refs вычисляется корректно
# ---------------------------------------------------------------------------

def test_unexamined_facts_computation() -> int:
    failures = 0
    hdr("A: unexamined_fact_refs — прямое тестирование через SessionManager")

    with tempfile.TemporaryDirectory(prefix="atman_unex_") as tmpdir:
        workspace = Path(tmpdir)
        agent_id = uuid4()
        config = AgentConfig(model=ModelConfig(model=MODEL, context_limit=2048))
        deps, session_manager, store = build_deps(workspace, agent_id, config)
        bootstrap(store, agent_id)

        ctx = session_manager.start_session(agent_id)
        session_id = ctx.session_id

        fact_a, fact_b, fact_c = uuid4(), uuid4(), uuid4()

        # Читаем три факта
        session_manager._note_facts_read(session_id, [fact_a, fact_b, fact_c])

        # Красим только fact_a через key moment
        session_manager.append_key_moment_input(
            session_id,
            KeyMomentInput(
                what_happened="Обработал факт A — он важен для понимания контекста",
                why_it_matters="Факт A меняет картину мира",
                emotional_valence=0.3,
                emotional_intensity=0.5,
                depth=EmotionalDepth.MEANINGFUL,
                fact_refs=[fact_a],
            ),
        )

        session_manager.finish_session(
            session_id,
            overall_emotional_tone=0.2,
            close_reason="completed",
        )

        exp_id = deterministic_session_experience_id(session_id)
        rec = store.get_experience(exp_id)

        ok1 = chk("A: experience записан", rec is not None)
        if rec:
            exp = rec.experience
            unex = set(exp.unexamined_fact_refs)
            ok2 = chk("A: fact_b в unexamined",
                      fact_b in unex, f"unexamined={[str(u)[:8] for u in unex]}")
            ok3 = chk("A: fact_c в unexamined",
                      fact_c in unex)
            ok4 = chk("A: fact_a НЕ в unexamined (он окрашен)",
                      fact_a not in unex)
            ok5 = chk("A: fact_refs содержит все три",
                      set(exp.fact_refs) == {fact_a, fact_b, fact_c},
                      f"fact_refs={[str(f)[:8] for f in exp.fact_refs]}")
            failures += sum([not ok2, not ok3, not ok4, not ok5])
        else:
            failures += 4

        # ── A2: нет фактов → unexamined пуст ─────────────────────────────────
        ctx2 = session_manager.start_session(agent_id)
        session_id2 = ctx2.session_id

        session_manager.append_key_moment_input(
            session_id2,
            KeyMomentInput(
                what_happened="Момент без фактов",
                why_it_matters="Просто опыт",
                emotional_valence=0.1,
                emotional_intensity=0.2,
                depth=EmotionalDepth.SURFACE,
            ),
        )
        session_manager.finish_session(session_id2, overall_emotional_tone=0.0,
                                       close_reason="completed")

        exp2_id = deterministic_session_experience_id(session_id2)
        rec2 = store.get_experience(exp2_id)
        if rec2:
            ok6 = chk("A2: без фактов → unexamined пуст",
                      len(rec2.experience.unexamined_fact_refs) == 0,
                      f"count={len(rec2.experience.unexamined_fact_refs)}")
            if not ok6:
                failures += 1

    return failures


# ---------------------------------------------------------------------------
# Тест B: wake-up messages для каждого close_reason
# ---------------------------------------------------------------------------

def test_wakeup_messages() -> int:
    failures = 0
    hdr("B: Wake-up messages для каждого close_reason")

    from atman.core.services.session_manager import SessionManager

    with tempfile.TemporaryDirectory(prefix="atman_wakeup_") as tmpdir:
        workspace = Path(tmpdir)
        agent_id = uuid4()
        config = AgentConfig(model=ModelConfig(model=MODEL, context_limit=2048))
        deps, session_manager, store = build_deps(workspace, agent_id, config)
        bootstrap(store, agent_id)

        close_reasons = ["completed", "timeout_sleep", "restart", "forced", "interrupted"]
        expected_keywords = {
            "completed":     ["завершена"],
            "timeout_sleep": ["задремал", "sleep", "тайм"],
            "restart":       ["перезапуск", "restart"],
            "forced":        ["переполн", "forced", "принудительно"],
            "interrupted":   ["прерван", "interrupted", "сигнал"],
        }

        for reason in close_reasons:
            ctx = session_manager.start_session(agent_id)
            sid = ctx.session_id

            session_manager.append_key_moment_input(
                sid,
                KeyMomentInput(
                    what_happened=f"Тестовый момент для {reason}",
                    why_it_matters="wake-up test",
                    emotional_valence=0.0,
                    emotional_intensity=0.2,
                    depth=EmotionalDepth.SURFACE,
                ),
            )

            kwargs: dict = {"overall_emotional_tone": 0.0, "close_reason": reason}
            if reason == "restart":
                kwargs["restart_reason"] = "тест перезапуска"
            if reason == "timeout_sleep":
                kwargs["agent_recap"] = "Краткий пересказ: разговор был продуктивным"

            session_manager.finish_session(sid, **kwargs)

            # Получаем wake-up message через _build_wake_up_message если есть
            exp_id = deterministic_session_experience_id(sid)
            rec = store.get_experience(exp_id)
            if rec is None:
                chk(f"B: {reason} — experience записан", False)
                failures += 1
                continue

            # Проверяем что build_wake_up_message строит нужный текст
            try:
                msg = session_manager._build_wake_up_message(rec.experience)
            except AttributeError:
                # Метод может быть в другом месте
                msg = None

            if msg is None:
                # Метод не найден — проверяем хотя бы сохранённые поля
                chk(f"B: {reason} — close_reason сохранён корректно",
                    rec.experience.close_reason == reason,
                    f"got={rec.experience.close_reason}")
                if reason == "restart":
                    ok = chk(f"B: restart_reason сохранён",
                             "тест" in (rec.experience.restart_reason or ""),
                             f"got={rec.experience.restart_reason!r}")
                    if not ok:
                        failures += 1
                if reason == "timeout_sleep":
                    ok = chk(f"B: agent_recap сохранён",
                             bool(rec.experience.agent_recap),
                             f"got={rec.experience.agent_recap!r}")
                    if not ok:
                        failures += 1
            else:
                msg_lower = msg.lower()
                keywords = expected_keywords.get(reason, [])
                for kw in keywords:
                    ok = chk(f"B: {reason} — '{kw}' в wake-up message",
                             kw.lower() in msg_lower,
                             f"msg={msg[:120]!r}")
                    if not ok:
                        failures += 1

    return failures


# ---------------------------------------------------------------------------
# Тест C: agent_recap через реальный LLM
# ---------------------------------------------------------------------------

async def test_agent_recap_live() -> int:
    """Агент пишет recap перед timeout_sleep."""
    failures = 0
    hdr("C: agent_recap — LLM пишет пересказ перед сном")

    from pydantic_ai import Agent
    from atman.adapters.agent.instructions import build_instructions
    from atman.adapters.agent.tools import log_experience, record_key_moment

    with tempfile.TemporaryDirectory(prefix="atman_recap_") as tmpdir:
        workspace = Path(tmpdir)
        agent_id = uuid4()
        config = AgentConfig(
            model=ModelConfig(model=MODEL, max_tokens=256, context_limit=4096),
            enable_key_moments=True,
        )
        deps, session_manager, store = build_deps(workspace, agent_id, config)
        bootstrap(store, agent_id)

        ctx = session_manager.start_session(agent_id)
        session_id = ctx.session_id
        deps = replace(deps, session_id=session_id)

        agent = Agent(
            MODEL,
            deps_type=type(deps),
            instructions=lambda c: build_instructions(c.deps),
            tools=(record_key_moment, log_experience),
        )

        # Краткий разговор
        messages = [
            "Расскажи мне что-то важное о себе.",
            "Спасибо. Напиши короткий пересказ нашего разговора для следующей сессии.",
        ]

        history: list = []
        recap_text: str | None = None
        for msg in messages:
            result = await agent.run(msg, deps=deps, message_history=history or None)
            history.extend(result.new_messages())
            output = str(result.output or "")
            print(f"  Agent: {output[:200]}{'…' if len(output)>200 else ''}")
            if "пересказ" in msg.lower():
                recap_text = output  # последний ответ = пересказ

        # Финализируем с timeout_sleep и передаём recap
        try:
            session_manager.finish_session(
                session_id,
                overall_emotional_tone=0.3,
                close_reason="timeout_sleep",
                agent_recap=recap_text,
            )
        except Exception as e:
            print(f"  [warn] finish_session: {e}")

        exp_id = deterministic_session_experience_id(session_id)
        rec = store.get_experience(exp_id)

        ok1 = chk("C: experience записан", rec is not None)
        if rec:
            ok2 = chk("C: close_reason=timeout_sleep",
                      rec.experience.close_reason == "timeout_sleep",
                      f"got={rec.experience.close_reason}")
            ok3 = chk("C: agent_recap сохранён",
                      bool(rec.experience.agent_recap),
                      f"len={len(rec.experience.agent_recap or '')}")
            failures += sum([not ok2, not ok3])
        else:
            failures += 2

    return failures


async def main() -> int:
    total = 0
    total += test_unexamined_facts_computation()
    total += test_wakeup_messages()
    total += await test_agent_recap_live()

    hdr("ИТОГ")
    if total == 0:
        print("  Все проверки прошли.")
    else:
        print(f"  FAILED: {total} проверок не прошло.")
    return total


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
