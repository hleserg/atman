#!/usr/bin/env bash
# scripts/docs/01_archive.sh
# Архивирует устаревшие файлы документации в docs/archive/2026-05/
# Запускать из корня репозитория: bash scripts/docs/01_archive.sh

set -e

ARCHIVE="docs/archive/2026-05"
mkdir -p "$ARCHIVE"

echo "→ Архивируем устаревшие файлы..."

# architecture/ — черновики и устаревший ops-doc
git mv "docs/architecture/SYSTEM 0.00.md"             "$ARCHIVE/" 2>/dev/null && echo "  ✓ SYSTEM 0.00.md" || echo "  – SYSTEM 0.00.md (не найден)"
git mv "docs/architecture/fullsystem 0.00.md"         "$ARCHIVE/" 2>/dev/null && echo "  ✓ fullsystem 0.00.md" || echo "  – fullsystem 0.00.md (не найден)"
git mv docs/architecture/DATADOG-LLM-OBSERVABILITY.md "$ARCHIVE/" 2>/dev/null && echo "  ✓ DATADOG-LLM-OBSERVABILITY.md" || echo "  – DATADOG-LLM-OBSERVABILITY.md (не найден)"

# development/ — устаревшие стандарты и неактуальные readme
git mv docs/development/GITHUB_AUTOMATIONS.md         "$ARCHIVE/" 2>/dev/null && echo "  ✓ GITHUB_AUTOMATIONS.md" || echo "  – GITHUB_AUTOMATIONS.md (не найден)"
git mv docs/development/README.md                     "$ARCHIVE/" 2>/dev/null && echo "  ✓ development/README.md" || echo "  – development/README.md (не найден)"
git mv docs/development/README_FACTUAL_MEMORY.md      "$ARCHIVE/" 2>/dev/null && echo "  ✓ README_FACTUAL_MEMORY.md" || echo "  – README_FACTUAL_MEMORY.md (не найден)"
git mv docs/development/TEST_COVERAGE_PLAN.md         "$ARCHIVE/" 2>/dev/null && echo "  ✓ TEST_COVERAGE_PLAN.md" || echo "  – TEST_COVERAGE_PLAN.md (не найден)"

# work-packages/ — устаревшие WP и вспомогательные файлы
git mv docs/development/work-packages/ISSUE_BACKLOG.md "$ARCHIVE/" 2>/dev/null && echo "  ✓ ISSUE_BACKLOG.md" || echo "  – ISSUE_BACKLOG.md (не найден)"
git mv docs/development/work-packages/README.md        "$ARCHIVE/" 2>/dev/null && echo "  ✓ work-packages/README.md" || echo "  – work-packages/README.md (не найден)"

git mv docs/development/work-packages/01-factual-memory-adapter.md "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-01" || echo "  – WP-01 (не найден)"
git mv docs/development/work-packages/02-experience-store.md       "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-02" || echo "  – WP-02 (не найден)"
git mv docs/development/work-packages/03-identity-and-narrative.md "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-03" || echo "  – WP-03 (не найден)"
git mv docs/development/work-packages/04-reflection-engine.md      "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-04" || echo "  – WP-04 (не найден)"
git mv docs/development/work-packages/05-session-manager.md        "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-05" || echo "  – WP-05 (не найден)"
git mv docs/development/work-packages/06-reality-and-affect.md     "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-06" || echo "  – WP-06 (не найден)"
git mv docs/development/work-packages/07-ambient-and-proactive.md  "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-07" || echo "  – WP-07 (не найден)"
git mv docs/development/work-packages/08-skill-manager.md          "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-08" || echo "  – WP-08 (не найден)"
git mv docs/development/work-packages/09-background-agent.md       "$ARCHIVE/" 2>/dev/null && echo "  ✓ WP-09" || echo "  – WP-09 (не найден)"

echo ""
echo "→ Добавляем README в архив (чтобы было понятно что это)"
cat > "$ARCHIVE/README.md" << 'EOF'
# Archive — May 2026

Files archived during docs restructuring (2026-05-19).

Reason: stale content — superseded by living codemap system and
updated component documentation. History preserved via git mv.

To restore any file:
  git mv docs/archive/2026-05/<filename> <target-path>
  git commit -m "docs: restore <filename> from archive"
EOF
git add "$ARCHIVE/README.md"

echo ""
echo "→ Коммитим..."
git commit -m "docs: archive stale files (WP 01-09, DATADOG, old drafts) [skip ci]"

echo ""
echo "✅ Готово. Архив: $ARCHIVE"
