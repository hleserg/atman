#!/usr/bin/env bash
# Ensure eval-only pip packages stay in [project.optional-dependencies] eval.
# PEP 621: dependencies is a key under [project], not [project.dependencies].

set -euo pipefail

# psycopg is in prod [project].dependencies — do not include it here.
EVAL_PKGS="datasets|evaluate|huggingface-hub|transformers|sqlalchemy|alembic|mem0ai|chromadb|qdrant-client"

violations=$(awk '
/^\[project\]$/{in_project=1; in_deps=0; next}
/^\[/ { in_project=0; in_deps=0; next }
in_project && /^dependencies[[:space:]]*=/ {
  in_deps=1
  if ($0 ~ /\]/) { in_deps=0 }
  next
}
in_project && in_deps {
  if (/^\]/) { in_deps=0; next }
  print
}
' pyproject.toml | grep -E "$EVAL_PKGS" || true)

if [ -n "$violations" ]; then
  echo "Eval-only packages found in [project].dependencies:"
  echo "$violations"
  echo "Move them to [project.optional-dependencies] eval"
  exit 1
fi

echo "pyproject.toml eval dependency placement OK"
