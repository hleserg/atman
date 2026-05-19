#!/usr/bin/env bash
# Ensure eval-only pip packages stay in [project.optional-dependencies] eval.

set -euo pipefail

EVAL_PKGS="datasets|evaluate|huggingface-hub|transformers|psycopg2|psycopg|sqlalchemy|alembic|mem0ai|chromadb|qdrant-client"

violations=$(awk '/^\[project\.dependencies\]/{found=1; next} /^\[/{found=0} found' pyproject.toml \
  | grep -E "$EVAL_PKGS" || true)

if [ -n "$violations" ]; then
  echo "Eval-only packages found in [project.dependencies]:"
  echo "$violations"
  echo "Move them to [project.optional-dependencies] eval"
  exit 1
fi

echo "pyproject.toml eval dependency placement OK"
