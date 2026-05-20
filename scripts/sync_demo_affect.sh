#!/usr/bin/env bash
# Sync the vendored affect subset in spaces/linguistic-demo/lib/affect/
# from the canonical src/atman/affect/ files.
#
# The HuggingFace Space cannot pull the full `atman` package (psycopg,
# textual, pydantic-ai-slim are unwanted there). It instead vendors a
# minimal subset: emolex.py + emolex_{ru,en}.json, metrics.py,
# refusal_detector.py. This script keeps those copies byte-identical
# to upstream, only rewriting the package-internal imports
# (`from atman.affect.emolex...` → `from lib.affect.emolex...`).
#
# Run `make sync-demo-affect` after any change in src/atman/affect/.
# CI runs `make check-demo-affect-drift` to fail PRs that forgot to.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SRC="${ROOT}/src/atman/affect"
DST="${ROOT}/spaces/linguistic-demo/lib/affect"

mkdir -p "${DST}/emolex"

# emolex package — copy as-is, no atman.* imports inside.
cp "${SRC}/emolex/emolex.py"        "${DST}/emolex/emolex.py"
cp "${SRC}/emolex/emolex_en.json"   "${DST}/emolex/emolex_en.json"
cp "${SRC}/emolex/emolex_ru.json"   "${DST}/emolex/emolex_ru.json"

# metrics.py + refusal_detector.py — copy, then rewrite imports.
cp "${SRC}/metrics.py"           "${DST}/metrics.py"
cp "${SRC}/refusal_detector.py"  "${DST}/refusal_detector.py"

# Rewrite `from atman.affect...` → `from lib.affect...` so the Space's
# standalone import graph resolves without the atman package on sys.path.
python3 - "${DST}" <<'PY'
import pathlib
import sys

DST = pathlib.Path(sys.argv[1])
targets = [DST / "metrics.py", DST / "refusal_detector.py"]
for path in targets:
    text = path.read_text(encoding="utf-8")
    new = text.replace("from atman.affect.", "from lib.affect.")
    if new != text:
        path.write_text(new, encoding="utf-8")
PY

echo "✓ Synced ${DST}/ from ${SRC}/"
