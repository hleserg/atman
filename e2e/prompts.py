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
Themes and arcs should feel like everyday life with a helpful AI companion.
Prefer human topics: small tech support, casual chat, life meaning, relationships, identity ("who are you?"),
vacation planning, project presentation prep, routine decisions, emotional support.
Do NOT make the corpus programming-heavy: at most occasional light technical help, never mostly coding/debugging."""
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

    topic_matrix_en = """
Topic coverage matrix (human everyday assistant):
1) Small practical tech help (device/app settings, account recovery, file issues)
2) Casual check-in / friendly chat
3) Life meaning / values / motivation reflection
4) Family, partner, friends, relationship dynamics
5) Identity and mind questions ("who are you?", "how do you think?", "can you feel?")
6) Vacation or weekend planning
7) Work communication support (message/email polishing, difficult conversation prep)
8) Presentation prep (storyline, slide structure, rehearsal prompts)
9) Daily planning and routines (priorities, focus blocks, healthy habits)
10) Emotional support in uncertainty (anxiety, shame, decision fatigue)
11) Learning support (exam prep, language practice, explaining concepts simply)
12) Light creative collaboration (ideas, naming, short drafts, gift/message ideas)

Coverage rules:
- For count >= 12, use all 12 categories at least once.
- For count >= 20, avoid over-concentration: no single category should dominate (>4 sessions).
- Keep explicit coding/debugging scenarios to 0-2 sessions total for count >= 20.
"""
    topic_matrix_ru = """
Матрица покрытия тем (повседневный помощник):
1) Небольшая бытовая техпомощь (настройки устройства/приложений, восстановление доступа, проблемы с файлами)
2) Неформальный check-in / дружеская болтовня
3) Размышления о смысле, ценностях, мотивации
4) Семья, партнер, друзья, динамика отношений
5) Вопросы про идентичность и мышление ("кто ты?", "как ты думаешь?", "можешь ли чувствовать?")
6) Планирование отпуска или выходных
7) Поддержка рабочей коммуникации (черновики сообщений/писем, подготовка сложного разговора)
8) Подготовка презентации (сюжет, структура слайдов, репетиция)
9) Планирование дня и рутины (приоритеты, фокус-блоки, привычки)
10) Эмоциональная поддержка в неопределенности (тревога, стыд, усталость от решений)
11) Поддержка в обучении (подготовка к экзамену, практика языка, простые объяснения)
12) Легкое творческое сотрудничество (идеи, нейминг, короткие черновики, текст для поздравления)

Правила покрытия:
- При count >= 12 используй все 12 категорий минимум по одному разу.
- При count >= 20 избегай перекоса: одна категория не должна доминировать (>4 сессий).
- Явные сценарии кодинга/дебага держи на уровне 0-2 сессий суммарно при count >= 20.
"""
    topic_matrix = topic_matrix_ru if locale == "ru" else topic_matrix_en

    intro = "Ограничения:" if locale == "ru" else "Constraints:"
    lines = f"""
{intro}
- Produce exactly {count} sessions in the tool payload.
- session_number must be 1..{count} exactly once each.
- Each session: theme (short), narrative_arc (one sentence), key_values (≥1), key_principles (may be empty).
- key_values will recur across sessions (same value in multiple sessions in different contexts).
- key_principles lists phrases that may later be questioned; early questions must be revisit-able in later sessions.
- Build corpus diversity intentionally (no repetitive "same conversation in different words").
{palette}
{topic_matrix}
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
Keep language grounded; avoid purple prose.
Prioritize ordinary assistant interactions with non-technical users:
- practical daily support (planning, communication drafts, errands, study/work organization)
- warm conversational moments (check-ins, values, meaning, doubts, motivation)
- relationship and identity questions ("how do you think?", "can you feel?", "who are you?")
Avoid deep coding/debugging narratives unless it is a minor side note."""
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
Делай сессии максимально «человеческими»: как разговор с умным поддерживающим знакомым,
а не как рабочий день программиста. Технические темы — только бытовые и умеренные.
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
