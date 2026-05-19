#!/usr/bin/env python3
"""
scripts/docs/04_add_codemap_markers.py

Добавляет <!-- codemap:auto:start section="docs-structure" --> маркеры
в AGENTS.md и .cursor/rules (или .cursorrules).

Идемпотентный: если маркер уже есть — пропускает файл.

Запуск из корня репозитория:
    python scripts/docs/04_add_codemap_markers.py
    python scripts/docs/04_add_codemap_markers.py --dry-run
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# ── Маркер + контент блока ────────────────────────────────────────────────────

DOCS_STRUCTURE_BLOCK = """\
<!-- codemap:auto:start section="docs-structure" -->
## Current Docs Map
<!-- Updated automatically by `make codemap`. Do not edit. -->
<!-- codemap:auto:end -->"""

# ── Блок для AGENTS.md (вставляется как новый раздел) ────────────────────────

AGENTS_SECTION = """
## Documentation Structure

Before creating any documentation file, check where it belongs.
Full spec: `docs/design/DESIGN_docs_structure.md`

| You're writing... | Put it in |
|-------------------|-----------|
| Architecture decision (stable, reviewed) | `docs/architecture/ADR/ADR-NNN-title.md` |
| Design doc (in progress) | `docs/design/DESIGN_*.md` |
| Feature user guide | `docs/features/<slug>/README.md` + `README-ru.md` |
| Work package / task spec | `docs/development/work-packages/NN-name.md` |
| Ops runbook (install, monitor, debug) | `docs/ops/` |
| Research / experiment | `docs/research/` |
| Hypothesis, not yet started | `docs/ideas/` |
| Session / implementation report | `reports/` |

Rules:
- `docs/architecture/`, `docs/design/`, `docs/ops/` require a `-ru.md` pair (EN first).
- `docs/content/` is auto-managed — never edit files there directly.
- Blocks between `<!-- codemap:auto:start -->` and `<!-- codemap:auto:end -->` are
  auto-updated by `make codemap`. Do not edit those blocks manually.

<!-- codemap:auto:start section="docs-structure" -->
## Current Docs Map
<!-- Updated automatically by `make codemap`. Do not edit. -->
<!-- codemap:auto:end -->
"""

# ── Блок для .cursor/rules (добавляется в конец) ─────────────────────────────

CURSOR_SECTION = """
## Documentation Placement

When creating or modifying documentation, always place files correctly:

- Architecture decisions (stable) → `docs/architecture/ADR/`
- Design docs (evolving) → `docs/design/DESIGN_*.md`
- Feature guides → `docs/features/<slug>/README.md` + `README-ru.md`
- Work packages → `docs/development/work-packages/`
- Ops runbooks → `docs/ops/`
- Research → `docs/research/`
- Ideas → `docs/ideas/`

Never:
- Create docs in repo root (only README/MANIFEST/AGENTS allowed there)
- Edit files in `docs/content/` (auto-overwritten on sync)
- Edit blocks between `<!-- codemap:auto:start -->` and `<!-- codemap:auto:end -->`

Every doc in `docs/architecture/`, `docs/design/`, `docs/ops/` needs a `-ru.md` pair.

<!-- codemap:auto:start section="docs-structure" -->
## Current Docs Map
<!-- Updated automatically by `make codemap`. Do not edit. -->
<!-- codemap:auto:end -->
"""

MARKER = '<!-- codemap:auto:start section="docs-structure" -->'

# ── Поиск .cursor/rules файла ─────────────────────────────────────────────────

CURSOR_CANDIDATES = [
    ".cursor/rules",
    ".cursor/rules.md",
    ".cursorrules",
]


def find_cursor_rules(repo_root: Path) -> Path | None:
    for candidate in CURSOR_CANDIDATES:
        p = repo_root / candidate
        if p.exists():
            return p
    return None


# ── Поиск точки вставки в AGENTS.md ──────────────────────────────────────────

# Пробуем найти один из этих заголовков — вставим ПОСЛЕ него
AGENTS_ANCHOR_AFTER = [
    "## Key Files",
    "## Key files",
    "## Important Files",
    "## Navigation",
    "## Project Structure",
    "## Repo Structure",
    "## Structure",
    "## Before You Start",
    "## Before you start",
    "## Getting Started",
    "## Context",
]

# Вставим ПЕРЕД этими заголовками (задачи/чеклист — документация должна быть раньше)
AGENTS_ANCHOR_BEFORE = [
    "## Task Checklist",
    "## Checklist",
    "## Rules",
    "## Constraints",
    "## Do Not",
    "## Important Rules",
    "## Code Style",
    "## Development",
]


def find_insertion_line(lines: list[str]) -> int:
    """
    Возвращает индекс строки ПОСЛЕ которой нужно вставить блок.
    Логика:
    1. Ищем якорь "после которого" — вставляем в конец этой секции
    2. Ищем якорь "перед которым" — вставляем прямо перед ним
    3. Fallback: в конец файла
    """
    # Попытка 1: найти "после" якорь, вставить в конец его секции
    for anchor in AGENTS_ANCHOR_AFTER:
        for i, line in enumerate(lines):
            if line.strip() == anchor or line.strip().startswith(anchor):
                # Найти конец этой секции (следующий ## заголовок или EOF)
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("## ") and j != i:
                        # Вставить перед следующей секцией
                        return j - 1
                # Если секция последняя — вставить в конец файла
                return len(lines) - 1

    # Попытка 2: найти "перед" якорь
    for anchor in AGENTS_ANCHOR_BEFORE:
        for i, line in enumerate(lines):
            if line.strip() == anchor or line.strip().startswith(anchor):
                return i - 1

    # Fallback: в конец файла
    return len(lines) - 1


# ── Основная логика ───────────────────────────────────────────────────────────

def patch_agents_md(repo_root: Path, dry_run: bool) -> bool:
    path = repo_root / "AGENTS.md"
    if not path.exists():
        print("  ⚠  AGENTS.md not found — skipping")
        return False

    content = path.read_text(encoding="utf-8")

    if MARKER in content:
        print("  ✓  AGENTS.md — marker already present, skipping")
        return False

    lines = content.splitlines(keepends=True)
    insert_after = find_insertion_line(lines)

    # Собираем новый контент
    block_lines = AGENTS_SECTION.splitlines(keepends=True)
    new_lines = lines[:insert_after + 1] + ["\n"] + block_lines + ["\n"] + lines[insert_after + 1:]
    new_content = "".join(new_lines)

    if dry_run:
        print(f"  DRY RUN — AGENTS.md: would insert after line {insert_after + 1}")
        print(f"           Anchor: {lines[insert_after].rstrip()!r}")
        print("           Preview of inserted block (first 3 lines):")
        for line in AGENTS_SECTION.strip().splitlines()[:3]:
            print(f"             {line}")
        print("             ...")
        return True

    path.write_text(new_content, encoding="utf-8")
    print(f"  ✓  AGENTS.md — marker inserted after line {insert_after + 1}")
    print(f"     Anchor: {lines[insert_after].rstrip()!r}")
    return True


def patch_cursor_rules(repo_root: Path, dry_run: bool) -> bool:
    path = find_cursor_rules(repo_root)

    if path is None:
        print("  ⚠  No .cursor/rules file found (tried: " + ", ".join(CURSOR_CANDIDATES) + ")")
        print("     Create one of those files first, then re-run this script.")
        return False

    content = path.read_text(encoding="utf-8")

    if MARKER in content:
        print(f"  ✓  {path} — marker already present, skipping")
        return False

    new_content = content.rstrip("\n") + "\n" + CURSOR_SECTION

    if dry_run:
        print(f"  DRY RUN — {path}: would append {len(CURSOR_SECTION.splitlines())} lines at end")
        return True

    path.write_text(new_content, encoding="utf-8")
    print(f"  ✓  {path} — marker appended at end")
    return True


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add codemap docs-structure markers to AGENTS.md and .cursor/rules"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing files")
    args = parser.parse_args()

    repo_root = Path(".")

    # Проверяем что запускаемся из корня репо
    if not (repo_root / "AGENTS.md").exists() and not find_cursor_rules(repo_root):
        print("ERROR: Run this script from the repository root.")
        sys.exit(1)

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Adding codemap markers...\n")

    agents_changed = patch_agents_md(repo_root, dry_run=args.dry_run)
    cursor_changed = patch_cursor_rules(repo_root, dry_run=args.dry_run)

    if not agents_changed and not cursor_changed:
        print("\nNothing to do — both files already have markers.")
        return

    if args.dry_run:
        print("\nDry run complete. Run without --dry-run to apply.")
        return

    print("\n── Next step ────────────────────────────────────────────────")
    files = []
    if agents_changed:
        files.append("AGENTS.md")
    if cursor_changed:
        cursor_path = find_cursor_rules(repo_root)
        if cursor_path:
            files.append(str(cursor_path))

    print("Review the changes, then commit:")
    print(f"  git diff {' '.join(files)}")
    print(f"  git add {' '.join(files)}")
    print('  git commit -m "docs: add codemap markers to agent instruction files [skip ci]"')


if __name__ == "__main__":
    main()
