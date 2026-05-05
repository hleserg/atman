# Session JSON fixtures (E2E)

JSON files describe **session-shaped** scenarios: `metadata`, `events`, `key_moments`,
and `expected_session_outcome`, aligned with `SessionEvent` / `KeyMomentInput` in
`atman.core.models.session`.

## Layout

- `en/session_<NN>_<slug>.json` — English dialogue and text fields.
- `ru/session_<NN>_<slug>.json` — Russian text; `event_type` values stay English for tooling.

## Generating fixtures

One-off LLM generation (not CI). Requires `ANTHROPIC_API_KEY` and `pip install -e ".[e2e]"`.

Default: **20 English + 20 Russian** sessions, **parallel** API runs:

```bash
pip install -e ".[e2e]"
export ANTHROPIC_API_KEY=...
python -m e2e.generate_fixtures --model claude-sonnet-4-6
```

Options:

- `--count-en N` / `--count-ru N` — per-locale session counts (0 skips that locale).
- `--no-parallel-locales` — generate locales one after another.
- `--count N` — legacy: English only, `N` sessions under `en/`.

**Always review and edit** before committing; model output is non-deterministic.

See [issue #141](https://github.com/hleserg/atman/issues/141).
