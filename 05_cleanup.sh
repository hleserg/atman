#!/usr/bin/env bash
# scripts/docs/05_cleanup.sh
# Архивирует ВСЁ кроме минимально необходимого.
# Запускать из корня репо: bash scripts/docs/05_cleanup.sh [--dry-run]

set -e

DRY=${1:-""}
ARCHIVE="docs/archive/2026-05"
mkdir -p "$ARCHIVE"

gmv() {
  local src="$1" dst="$2"
  if [ "$DRY" = "--dry-run" ]; then
    echo "  DRY: $src → $dst"
    return
  fi
  if [ -e "$src" ]; then
    git mv "$src" "$dst" && echo "  ✓ $src → $dst"
  else
    echo "  – $src (не найден)"
  fi
}

echo ""
echo "═══ docs/ — корень ═══"
gmv "docs/DATABASE_SCHEMA.md"               "$ARCHIVE/"
gmv "docs/WP-affect-detector.md"            "$ARCHIVE/"
gmv "docs/reflective-session-protocol.md"   "$ARCHIVE/"
gmv "docs/secure-contact-vault.md"          "$ARCHIVE/"

echo ""
echo "═══ docs/architecture/ — оставляем только SYSTEM* ═══"
gmv "docs/architecture/CODEBASE_IMPLEMENTATION_MAP_RU.md"        "$ARCHIVE/"
gmv "docs/architecture/EMBEDDING.md"                             "$ARCHIVE/"
gmv "docs/architecture/EMBEDDING-ru.md"                          "$ARCHIVE/"
gmv "docs/architecture/EVAL_STORAGE.md"                          "$ARCHIVE/"
gmv "docs/architecture/PROD_EVAL_BOUNDARY.md"                    "$ARCHIVE/"
gmv "docs/architecture/REFLECTIONS.md"                           "$ARCHIVE/"
gmv "docs/architecture/SESSION_LIFECYCLE.md"                     "$ARCHIVE/"
gmv "docs/architecture/ATMAN_MEMORY_AND_LINGUISTIC_FINAL_v3.md"  "$ARCHIVE/"
gmv "docs/architecture/MEMORY-ARCHITECTURE.md"                   "$ARCHIVE/"
gmv "docs/architecture/DATABASE_SCHEMA.md"                       "$ARCHIVE/"

echo ""
echo "═══ docs/development/ — оставляем только DEVELOPMENT_STANDARD.md ═══"
gmv "docs/development/LIVE_E2E_RUNBOOK.md"    "$ARCHIVE/"
gmv "docs/development/MEMORY-ARCHITECTURE.md" "$ARCHIVE/"
gmv "docs/development/PLAYBOOK_MARKERS.md"    "$ARCHIVE/"
gmv "docs/development/ROADMAP.md"             "$ARCHIVE/"
gmv "docs/development/SENTRY_SETUP.md"        "$ARCHIVE/"
for f in docs/development/work-packages/*.md; do
  [ -e "$f" ] && gmv "$f" "$ARCHIVE/"
done

echo ""
echo "═══ docs/ideas/ — всё в архив ═══"
for f in docs/ideas/*.md; do
  [ -e "$f" ] && gmv "$f" "$ARCHIVE/"
done

echo ""
echo "═══ docs/research/ — всё в архив ═══"
for f in docs/research/*; do
  [ -e "$f" ] && [ "$(basename "$f")" != ".gitkeep" ] && gmv "$f" "$ARCHIVE/"
done
if [ -e "docs/research/GPT about system" ]; then
  if [ "$DRY" = "--dry-run" ]; then
    echo "  DRY: 'GPT about system' → $ARCHIVE/GPT-about-system.md"
  else
    git mv "docs/research/GPT about system" "$ARCHIVE/GPT-about-system.md" \
      && echo "  ✓ GPT about system → archved"
  fi
fi

if [ "$DRY" = "--dry-run" ]; then
  echo ""
  echo "Dry run завершён. Запусти без --dry-run чтобы применить."
  exit 0
fi

echo ""
echo "═══ Коммит ═══"
git add -A
git commit -m "docs: nuclear cleanup — archive everything except essentials [skip ci]"

echo ""
echo "✅ Готово. Осталось:"
echo "   docs/architecture/  → SYSTEM.md, SYSTEM-ru.md, SYSTEM_MAP.md, SYSTEM_MAP-ru.md"
echo "   docs/development/   → DEVELOPMENT_STANDARD.md"
echo "   docs/features/      → */README.md + */README-ru.md"
echo "   docs/design/        → пусто (под новые design docs)"
echo "   docs/ops/           → пусто (под новые ops docs)"
echo "   docs/archive/2026-05/ → всё старое, история сохранена через git mv"
