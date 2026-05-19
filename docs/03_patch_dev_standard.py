#!/usr/bin/env python3
"""
scripts/docs/03_patch_dev_standard.py

Патчит docs/development/DEVELOPMENT_STANDARD.md:
  1. Заменяет §24 (Структура репозитория) — добавляет новые папки
     docs/ops/, docs/design/, docs/archive/, docs/architecture/ADR/,
     docs/architecture/codemap/ и обновляет правила для агентов.
  2. Добавляет §28 (Документация: где создавать и как вести).

Запускать из корня репозитория:
    python scripts/docs/03_patch_dev_standard.py [--dry-run]
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

TARGET = Path("docs/development/DEVELOPMENT_STANDARD.md")

# ─────────────────────────────────────────────────────────────────────────────
# §24 replacement
# ─────────────────────────────────────────────────────────────────────────────

OLD_24_ANCHOR = "## 24. Структура репозитория"

NEW_24 = """\
## 24. Структура репозитория

Каждый файл должен лежать в строго определённом месте.
Полная спецификация структуры `docs/` — в `docs/design/DESIGN_docs_structure.md`.
Правило простое: не знаешь куда — смотри таблицу ниже или спроси.

### Корень репозитория `/`

Только то, что GitHub и инструменты ожидают найти в корне:

```text
README.md / README-ru.md   — точка входа для людей
MANIFEST.md / MANIFEST-ru.md
AGENTS.md                  — инструкции для агентов (только EN)
CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / LICENSE
Makefile
pyproject.toml / uv.lock
.gitignore / .gitattributes / .markdownlint.json / .pre-commit-config.yaml
.github/                   — Actions workflows, шаблоны PR/issues
.cursor/                   — правила для Cursor
src/                       — исполняемый код
tests/                     — тесты
e2e/                       — end-to-end сценарии
fixtures/                  — тестовые фикстуры
reports/                   — отчёты о сессиях и реализации
scripts/                   — служебные скрипты (codemap, docs, eval)
```

Запрещено класть в корень: design-документы, отчёты, HTML-файлы сайта,
скрипты-демо, исследования, work packages, README к отдельным модулям.

### `/docs` — вся документация

```text
docs/
  architecture/            — ЧТО такое система (стабильное, прорецензированное)
    SYSTEM.md / -ru.md
    SYSTEM_MAP.md / -ru.md   ← авто-обновляется кодмапом
    ADR/                     ← Architecture Decision Records (ADR-NNN-title.md)
    codemap/                 ← авто-генерируется скриптом, не редактировать руками
      STARTUP_DEPS.md / -ru.md
      TEST_ENV.md / -ru.md
      ENDPOINTS.md / -ru.md
      DELTA_REPORT.md / -ru.md
      UNDOCUMENTED.md / -ru.md

  design/                  — КАК строим конкретные вещи (эволюционирует)
    DESIGN_*.md / -ru.md
    *-design.md / -ru.md

  development/             — процесс и стандарты
    DEVELOPMENT_STANDARD.md (этот файл)
    work-packages/           ← ТЗ на реализацию, NN-name.md

  features/                — пользовательские гайды по фичам
    <slug>/
      README.md / README-ru.md

  ops/                     — как запускать и эксплуатировать Atman
    УСТАНОВКА.md
    ...

  research/                — что изучалось; нет обязательства действовать
  ideas/                   — гипотезы, ещё не в работе
  archive/                 — устаревшее; только git mv, не удалять

  content/                 — копии для GitHub Pages; НЕ редактировать вручную
    README.md / -ru.md
    MANIFEST.md / -ru.md
    SYSTEM.md / -ru.md
    SYSTEM_MAP.md / -ru.md

  (ассеты сайта)
    CNAME / index.html / document.html / demo.html / pic/
```

### Быстрая таблица: куда класть новый документ

| Создаёшь... | Папка |
|-------------|-------|
| Архитектурное решение (принято, стабильно) | `docs/architecture/ADR/ADR-NNN-title.md` |
| Design doc (в процессе, эволюционирует) | `docs/design/DESIGN_*.md` |
| Гайд для пользователя фичи | `docs/features/<slug>/README.md` + `README-ru.md` |
| ТЗ на реализацию (work package) | `docs/development/work-packages/NN-name.md` |
| Операционный runbook (установка, мониторинг) | `docs/ops/` |
| Исследование, сравнение, эксперимент | `docs/research/` |
| Гипотеза, ещё не в работе | `docs/ideas/` |
| Отчёт о реализации / сессии | `reports/` |

### Правила для агентов

- **Создал новый документ** — найди строку в таблице выше; не знаешь — спроси.
- **Не создавай новые папки** в корне и в `docs/` без явного решения в PR.
- **Не редактируй `docs/content/`** — файлы там перезаписываются автоматически.
- **Не кладёт в `docs/archive/`** — туда только переносят через `git mv`.
- **Feature guide** (`docs/features/<slug>/`) — только пара `README.md` + `README-ru.md`.
- **Work package** — только в `docs/development/work-packages/`, имя `NN-name.md`.
- **ADR** — только в `docs/architecture/ADR/`, имя `ADR-NNN-short-title.md`.
- **Design doc** — префикс `DESIGN_` или суффикс `-design.md`.
- **Двуязычность**: `docs/architecture/`, `docs/design/`, `docs/ops/` требуют `-ru.md` пару.
  EN пишется первым, RU — следом. `docs/research/` и `docs/ideas/` — RU опционально.
- **`SYSTEM_MAP.md`**: обновляется кодмапом автоматически (§1 таблицы).
  §2–§5 (сценарии, edge cases, регрессии) — обновлять руками в том же PR, что и код.
- **`README.md` / `MANIFEST.md` / `SYSTEM.md`**: правишь EN → сразу синхронизируй RU →
  запусти `make sync-site-content` (обновит `docs/content/`).
- **Скрипты-демо** (`demo.py`, `full_demo.sh`) — в `src/` или удалить после merge.
- **`uv`**: для установки и запуска предпочитать `uv run`, `uv pip install`.
"""

# ─────────────────────────────────────────────────────────────────────────────
# §28 — новый раздел
# ─────────────────────────────────────────────────────────────────────────────

NEW_28 = """
## 28. Документация: когда создавать и что писать

### 28.1 Обязательные артефакты при merge PR

Каждый PR, который добавляет или меняет поведение системы, обязан включать:

| Изменение в коде | Обязательный doc-артефакт |
|------------------|--------------------------|
| Новый work package / компонент | `docs/development/work-packages/NN-name.md` |
| Реализованная фича (публичный CLI / API) | `docs/features/<slug>/README.md` + `README-ru.md` |
| Архитектурное решение (breaking change, новый сервис) | `docs/architecture/ADR/ADR-NNN-title.md` |
| Новый порт, адаптер, сервис | обновление `SYSTEM_MAP.md` (§1 маркеры, §2 проводка) |
| Новая CLI-команда | обновление `docs/architecture/codemap/ENDPOINTS.md` (авто при `make codemap`) |
| Новая env-переменная | обновление `.env.example` + `docs/architecture/codemap/STARTUP_DEPS.md` |

PR без нужного doc-артефакта не готов к merge. Исключение: правки в тестах,
опечатки, рефакторинг без изменения публичного контракта — можно указать
`docs: N/A — internal refactor` в описании PR.

### 28.2 Язык документов

- `docs/architecture/`, `docs/design/`, `docs/ops/` — **EN канонический**, RU следом.
- `docs/features/<slug>/README.md` — **EN канонический**, `README-ru.md` следом.
- `docs/development/work-packages/` — **RU** (агент пишет ТЗ на русском для понимания).
- `docs/research/`, `docs/ideas/` — любой язык, RU-пара опциональна.
- `AGENTS.md` — только **EN** (агенты работают на английском).
- `MANIFEST.md`, `SYSTEM.md` — **EN + RU**, оба файла обязательны.

### 28.3 Что писать в design doc (docs/design/)

Минимальная структура `DESIGN_*.md`:

```markdown
# Design — <Title>

> **Type:** Design document
> **Status:** Draft | Review | Decided
> **Date:** YYYY-MM-DD
> **Location:** docs/design/DESIGN_<name>.md

## 1. Problem
<Что не работает или чего не хватает — конкретно.>

## 2. Decision
<Что делаем. Достаточно конкретно чтобы агент мог реализовать без уточнений.>

## 3. Out of scope
<Что явно НЕ входит в это решение.>

## 4. Open questions
<Что ещё не решено. Если пусто — удалить раздел.>
```

Когда design принят → ADR в `docs/architecture/ADR/`.

### 28.4 Что писать в ADR (docs/architecture/ADR/)

```markdown
# ADR-NNN — <Short title>

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNN
**Date:** YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
## Migration impact
```

ADR обязателен (см. §22) при: новом обязательном сервисе, breaking schema change,
смене lifecycle, смене storage boundary, новом типе памяти.

### 28.5 Авто-обновление документации

Скрипт `make codemap` обновляет автоматически:
- `docs/architecture/SYSTEM_MAP.md` — §1 таблицы (модули, порты, адаптеры)
- `docs/architecture/codemap/*` — STARTUP_DEPS, TEST_ENV, ENDPOINTS, DELTA, UNDOCUMENTED
- `README.md` — roadmap-блок и список готовых компонентов
- `AGENTS.md` и `.cursor/rules` — блок с картой документации

Агент **не должен** редактировать эти блоки вручную — правки будут перезаписаны.
Блоки обёрнуты маркерами `<!-- codemap:auto:start ... -->`.

Запускать перед коммитом: `make codemap`. CI упадёт если маркеры устарели.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Patching logic
# ─────────────────────────────────────────────────────────────────────────────

def find_section_bounds(lines: list[str], anchor: str) -> tuple[int, int]:
    """
    Return (start, end) line indices for a ## section starting with anchor.
    end is the line index of the next ## section (exclusive), or len(lines).
    """
    start = None
    for i, line in enumerate(lines):
        if line.startswith(anchor):
            start = i
            break
    if start is None:
        raise ValueError(f"Anchor not found: {anchor!r}")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ") and i != start:
            end = i
            break
    return start, end


def section_27_end(lines: list[str]) -> int:
    """Return the line index just after §27 ends (before §28 if it exists)."""
    anchor = "## 27. Принцип безопасности смысла"
    try:
        start, end = find_section_bounds(lines, anchor)
        return end
    except ValueError:
        return len(lines)


def apply_patch(content: str, dry_run: bool = False) -> str:
    lines = content.splitlines(keepends=True)

    # ── Replace §24 ──────────────────────────────────────────────────────────
    try:
        s24, e24 = find_section_bounds(lines, OLD_24_ANCHOR)
    except ValueError:
        print("ERROR: Could not find §24 anchor in file. Aborting.", file=sys.stderr)
        sys.exit(1)

    new_24_lines = (NEW_24.lstrip("\n") + "\n").splitlines(keepends=True)
    lines = lines[:s24] + new_24_lines + lines[e24:]
    print(f"  ✓ §24 replaced ({e24 - s24} lines → {len(new_24_lines)} lines)")

    # ── Append §28 (or replace if exists) ────────────────────────────────────
    # Recompute after §24 replacement
    s28_anchor = "## 28. Документация"
    existing_s28 = None
    for i, line in enumerate(lines):
        if line.startswith(s28_anchor):
            existing_s28 = i
            break

    new_28_lines = (NEW_28.lstrip("\n") + "\n").splitlines(keepends=True)

    if existing_s28 is not None:
        _, e28 = find_section_bounds(lines, s28_anchor)
        lines = lines[:existing_s28] + new_28_lines + lines[e28:]
        print(f"  ✓ §28 replaced (was {e28 - existing_s28} lines → {len(new_28_lines)} lines)")
    else:
        # Insert after §27
        insert_at = section_27_end(lines)
        lines = lines[:insert_at] + new_28_lines + lines[insert_at:]
        print(f"  ✓ §28 inserted after §27 ({len(new_28_lines)} lines)")

    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch DEVELOPMENT_STANDARD.md")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print result to stdout instead of writing file")
    args = parser.parse_args()

    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from repo root.", file=sys.stderr)
        sys.exit(1)

    original = TARGET.read_text(encoding="utf-8")
    print(f"Patching {TARGET} ...")

    patched = apply_patch(original, dry_run=args.dry_run)

    if args.dry_run:
        print("\n── DRY RUN — result (first 120 chars per line) ──")
        for line in patched.splitlines():
            print(" ", line[:120])
        return

    TARGET.write_text(patched, encoding="utf-8")
    print(f"\n✅ Done. Commit with:")
    print(f'   git add {TARGET}')
    print(f'   git commit -m "docs(standard): update §24 repo structure + add §28 doc rules [skip ci]"')


if __name__ == "__main__":
    main()
