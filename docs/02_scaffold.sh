#!/usr/bin/env bash
# scripts/docs/02_scaffold.sh
# Создаёт новую структуру папок документации
# Запускать из корня репозитория ПОСЛЕ 01_archive.sh

set -e

echo "→ Создаём новые папки..."

mkdir -p docs/ops
mkdir -p docs/design
mkdir -p docs/architecture/ADR
mkdir -p docs/architecture/codemap
mkdir -p docs/archive/2026-05   # уже есть, но на всякий случай

# Gitkeep для пустых папок
touch docs/ops/.gitkeep
touch docs/design/.gitkeep
touch docs/architecture/ADR/.gitkeep
touch docs/architecture/codemap/.gitkeep

echo "  ✓ docs/ops/"
echo "  ✓ docs/design/"
echo "  ✓ docs/architecture/ADR/"
echo "  ✓ docs/architecture/codemap/"

# INDEX файл для каждой новой папки
cat > docs/ops/README.md << 'EOF'
# docs/ops — Operational Documentation

How to run, configure, monitor, and debug Atman.

## Contents (add files here as they are created)

| File | Purpose |
|------|---------|
| *(empty — to be filled)* | |

## What belongs here
- Installation and setup guides
- Infrastructure reference (ports, services, connection strings)
- Monitoring and observability setup
- Health check procedures
- Backup and restore

## What does NOT belong here
- Architecture decisions → `docs/architecture/`
- Feature guides → `docs/features/<slug>/`
- Design documents → `docs/design/`
EOF

cat > docs/design/README.md << 'EOF'
# docs/design — Design Documents

How specific components and systems are being built.
Documents here evolve; they are not final architecture records.
When a design is decided → write an ADR in `docs/architecture/ADR/`.

## Contents (add files here as they are created)

| File | Purpose |
|------|---------|
| *(empty — to be filled)* | |

## What belongs here
- DESIGN_*.md files
- Component design docs (*-design.md, *-system-design.md)
- Feature specifications
- Future plans (REFLECTION_FUTURE.md etc.)

## What does NOT belong here
- Stable architecture → `docs/architecture/`
- User guides → `docs/features/<slug>/`
- Research → `docs/research/`
EOF

cat > docs/architecture/ADR/README.md << 'EOF'
# Architecture Decision Records

One file per architectural decision. Format: `ADR-NNN-short-title.md`

Each ADR contains:
- Context
- Decision
- Alternatives considered
- Consequences
- Migration impact

## Decisions

| ADR | Title | Status |
|-----|-------|--------|
| *(none yet — to be created)* | | |
EOF

git add -A
git commit -m "docs: scaffold new structure (ops/, design/, ADR/, codemap/) [skip ci]"

echo ""
echo "✅ Структура создана:"
echo ""
find docs -type d | sort | sed 's/^/  /'
