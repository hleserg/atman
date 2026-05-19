#!/usr/bin/env python3
"""
scripts/docs/06_inject_system_map_markers.py

Вставляет <!-- codemap:auto:start --> маркеры в существующий SYSTEM_MAP.md.
НЕ трогает содержимое таблиц — только оборачивает их маркерами.
Идемпотентный: если маркер уже есть в секции — пропускает.

Запуск: python3 scripts/docs/06_inject_system_map_markers.py [--dry-run]
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

TARGET = Path("docs/architecture/SYSTEM_MAP.md")

# Маркеры которые нужно вставить.
# key = название секции (section="X"), value = заголовок ### который её предваряет
SECTIONS = {
    "modules-domain-models": "### 1.1.",
    "modules-ports":         "### 1.2.",
    "modules-services":      "### 1.3.",
    "modules-adapters":      "### 1.4.",
    "modules-cli":           "### 1.5.",
}

START_TMPL = '<!-- codemap:auto:start section="{section}" -->'
END_TAG    = "<!-- codemap:auto:end -->"
MARKER_RE  = re.compile(r'<!--\s*codemap:auto:start')


def find_section_table_bounds(lines: list[str], header_prefix: str) -> tuple[int, int] | None:
    """
    Найти строки таблицы под заголовком header_prefix.
    Возвращает (first_table_line, last_table_line) — inclusive индексы.
    None если секция не найдена или таблицы нет.
    """
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith(header_prefix):
            header_idx = i
            break
    if header_idx is None:
        return None

    # Найти первую строку таблицы после заголовка
    table_start = None
    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("|"):
            table_start = i
            break
        # Если наткнулись на следующий ### — таблицы нет
        if stripped.startswith("### ") and i != header_idx:
            return None

    if table_start is None:
        return None

    # Найти конец таблицы (последняя строка начинается с |)
    table_end = table_start
    for i in range(table_start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("|"):
            table_end = i
        elif stripped == "":
            continue
        else:
            break

    return table_start, table_end


def inject_markers(content: str, dry_run: bool = False) -> str:
    lines = content.splitlines(keepends=True)
    # Работаем с конца чтобы индексы не сдвигались
    sections_sorted = sorted(SECTIONS.items(), key=lambda kv: kv[1], reverse=True)

    changes = []

    for section, header_prefix in sections_sorted:
        # Проверить что маркер ещё не стоит
        start_tag = START_TMPL.format(section=section)
        if any(start_tag in line for line in lines):
            print(f"  – {section}: маркер уже есть, пропускаем")
            continue

        bounds = find_section_table_bounds(lines, header_prefix)
        if bounds is None:
            print(f"  ⚠ {section}: секция '{header_prefix}' или таблица не найдена")
            continue

        table_start, table_end = bounds

        if dry_run:
            print(f"  DRY {section}: обернуть строки {table_start+1}–{table_end+1} "
                  f"(заголовок: {lines[table_start-1].rstrip()!r})")
            changes.append(section)
            continue

        # Вставить END после последней строки таблицы
        lines.insert(table_end + 1, END_TAG + "\n")
        # Вставить START перед первой строкой таблицы
        lines.insert(table_start, start_tag + "\n")

        print(f"  ✓ {section}: маркеры вставлены вокруг строк {table_start+1}–{table_end+1}")
        changes.append(section)

    return "".join(lines), changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not TARGET.exists():
        print(f"ERROR: {TARGET} не найден. Запускай из корня репо.")
        sys.exit(1)

    content = TARGET.read_text(encoding="utf-8")
    print(f"\nИнжектируем маркеры в {TARGET} ...\n")

    result, changes = inject_markers(content, dry_run=args.dry_run)

    if args.dry_run:
        if changes:
            print(f"\nDry run: будет изменено {len(changes)} секций.")
        else:
            print("\nDry run: нечего менять.")
        return

    if not changes:
        print("\nНичего не изменилось.")
        return

    TARGET.write_text(result, encoding="utf-8")
    print(f"\n✅ Готово. Изменено секций: {len(changes)}")
    print("\nСледующий шаг:")
    print("  python3 -m scripts.codemap --no-coverage --lang en")
    print("  git diff docs/architecture/SYSTEM_MAP.md")


if __name__ == "__main__":
    main()
