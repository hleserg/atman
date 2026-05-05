"""System and user prompts for two-pass fixture generation (locales: en, ru)."""

from __future__ import annotations

import json
from typing import Any, Literal

from e2e.models import SessionSkeletonItem

Locale = Literal["en", "ru"]


def skeleton_system(locale: Locale) -> str:
    base = """You are a careful writer of realistic agent session scenarios for testing.
You output ONLY via the provided tool — no prose outside tool calls.
Sessions form one chronological corpus: later sessions may reference emotional residue from earlier ones.
Use concrete, grounded language; avoid melodrama or grand claims.
Themes and arcs should be plausible work sessions (coding, planning, user dialogue)."""
    if locale == "ru":
        return (
            base
            + """

Locale RU: All human-readable strings in the tool payload MUST be in Russian:
metadata.theme, metadata.narrative_arc, event descriptions, key_moment text fields,
expected_session_outcome.key_insight, SessionSkeletonItem narrative_arc/theme/key_values strings.
Keep JSON keys and event_type values in English (e.g. user_message, agent_response) for tooling."""
        )
    return (
        base
        + """

Locale EN: All human-readable strings in the tool payload MUST be in English."""
    )


def skeleton_user_prompt(count: int, locale: Locale) -> str:
    palette = ""
    if count == 5:
        palette_en = """
Required emotional palette across the five sessions (map sessions 1→5 in order):
1) Routine / neutral — low drama, everyday progress.
2) Breakthrough / clearly positive outcome.
3) Doubt about a principle or habit — mixed affect, questioning.
4) Values conflict or setback — overall negative tone allowed.
5) Integration / deep positive insight — coherent closure referencing earlier threads.

"""
        palette_ru = """
Требуемая эмоциональная палитра по пяти сессиям (по порядку 1→5):
1) Рутина / нейтрально — мало драмы, обычный прогресс.
2) Прорыв / явно позитивный исход.
3) Сомнение в принципе или привычке — смешанный тон, вопросы.
4) Конфликт ценностей или откат — допустим отрицательный общий тон.
5) Интеграция / глубокий позитивный инсайт — связное завершение с отсылками к ранним нитям.

"""
        palette = palette_ru if locale == "ru" else palette_en

    intro = "Ограничения:" if locale == "ru" else "Constraints:"
    lines = f"""
{intro}
- Produce exactly {count} sessions in the tool payload.
- session_number must be 1..{count} exactly once each.
- Each session: theme (short), narrative_arc (one sentence), key_values (≥1), key_principles (may be empty).
- key_values will recur across sessions (same value in multiple sessions in different contexts).
- key_principles lists phrases that may later be questioned; early questions must be revisit-able in later sessions.
{palette}
"""
    return lines.strip()


def session_system(locale: Locale) -> str:
    base = """You are writing one JSON session fixture for an AI agent psychology layer.
Output ONLY via the provided tool. Events are raw; key moments are first-hand colored experience.
Each key moment's what_happened must clearly refer to a concrete earlier event (by situation, not by ID).
principles_questioned items MUST appear in wording or paraphrase in an event description BEFORE that moment.
expected_session_outcome.overall_emotional_tone must equal (within 0.1 of) the intensity-weighted mean
of emotional_valence over key_moments, using weights emotional_intensity. Use 3–5 events and 2–3 key moments.
metadata.duration_seconds should be plausible (e.g. 900–7200).
Keep language grounded; avoid purple prose."""
    if locale == "ru":
        return (
            base
            + """

Locale RU: metadata, events descriptions, all key_moment text fields, key_insight MUST be in Russian.
event_type stays in English. values_touched / principles_* may be Russian short tokens or Latin — be consistent."""
        )
    return base + "\n\nLocale EN: all user-visible text in English."


def session_user_prompt(
    skeleton: SessionSkeletonItem,
    prior_fixtures_summary: list[dict[str, Any]],
    locale: Locale,
) -> str:
    prior_json = json.dumps(prior_fixtures_summary, ensure_ascii=False, indent=2)
    sk_json = skeleton.model_dump_json(indent=2)
    if locale == "ru":
        return f"""Зафиксированный скелет этой сессии (соблюдай тему, арку, ценности, принципы):
{sk_json}

Предыдущие сессии корпуса (для преемственности — можно отозвать ценности или оспоренные принципы):
{prior_json}

Заполни инструмент полной сессией: metadata (session_number и theme как в скелете),
events, key_moments, expected_session_outcome.
metadata.narrative_arc — одно предложение, согласованное со скелетом narrative_arc.
""".strip()
    return f"""Fixed skeleton for this session (obey theme, arc, values, principles):
{sk_json}

Prior sessions in this corpus (for continuity — you may echo values or revisit questioned principles):
{prior_json}

Fill the tool with the full session: metadata (match session_number and theme from skeleton),
events, key_moments, expected_session_outcome.
metadata.narrative_arc should match or refine the skeleton narrative_arc in one sentence.
""".strip()


def retry_prefix(hint: str, locale: Locale) -> str:
    if locale == "ru":
        return (
            f"Предыдущая попытка отклонена:\n{hint}\n\n"
            f"Исправь JSON под ограничения и снова вызови инструмент.\n\n"
        )
    return (
        f"The previous attempt was rejected:\n{hint}\n\n"
        f"Fix the JSON to satisfy constraints and call the tool again.\n\n"
    )
