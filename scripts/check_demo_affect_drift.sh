#!/usr/bin/env bash
# Check that spaces/linguistic-demo/lib/affect/ is up to date with the
# canonical src/atman/affect/ source. Fails with non-zero exit and a
# unified diff when out of sync — call from CI to catch forgotten
# manual propagations.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# Re-run the sync into a tmp tree, then diff each file against the
# committed vendored copy. We do this by temporarily relocating the
# vendor directory inside the tmp git workspace and running sync,
# but the simpler approach: copy expected outputs into TMP and diff.

mkdir -p "${TMP}/emolex"
cp "${ROOT}/src/atman/affect/emolex/emolex.py"        "${TMP}/emolex/emolex.py"
cp "${ROOT}/src/atman/affect/emolex/emolex_en.json"   "${TMP}/emolex/emolex_en.json"
cp "${ROOT}/src/atman/affect/emolex/emolex_ru.json"   "${TMP}/emolex/emolex_ru.json"
cp "${ROOT}/src/atman/affect/metrics.py"              "${TMP}/metrics.py"
cp "${ROOT}/src/atman/affect/refusal_detector.py"     "${TMP}/refusal_detector.py"

python3 - "$TMP" <<'PY'
import pathlib, sys
TMP = pathlib.Path(sys.argv[1])
for name in ("metrics.py", "refusal_detector.py"):
    p = TMP / name
    p.write_text(
        p.read_text(encoding="utf-8").replace("from atman.affect.", "from lib.affect."),
        encoding="utf-8",
    )
PY

VENDOR="${ROOT}/spaces/linguistic-demo/lib/affect"
status=0
for rel in emolex/emolex.py emolex/emolex_en.json emolex/emolex_ru.json metrics.py refusal_detector.py; do
    if ! diff -u "${VENDOR}/${rel}" "${TMP}/${rel}" > /dev/null; then
        echo "✗ Drift in ${rel}:"
        diff -u "${VENDOR}/${rel}" "${TMP}/${rel}" | head -40
        status=1
    fi
done

if [[ $status -ne 0 ]]; then
    echo ""
    echo "Run 'make sync-demo-affect' to refresh vendored copies." >&2
    exit 1
fi
echo "✓ Vendored spaces/linguistic-demo/lib/affect/ is in sync with src/atman/affect/"
