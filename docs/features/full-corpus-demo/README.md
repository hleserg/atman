# Full corpus demo

Replays **all** session-shaped JSON fixtures under `e2e/fixtures/sessions/{en,ru}/` through the integrated stack:

1. **FileStateStore** — bootstrap identity + narrative  
2. **SessionManager** — per fixture: events, key moments, finish → experience + eigenstate + narrative touch  
3. **MicroReflectionService** — after each session  
4. **DailyReflectionService** — one UTC calendar day per session (deterministic spacing)  
5. **DeepReflectionService** — once over the full time span  

Reflection uses the **deterministic mock** from `e2e/full_loop` (no API keys). The closing table compares bootstrap state vs accumulated experiences, principle touches in key moments, mood samples, patterns, reframing notes, and narrative **recent** layer text.

## Run

```bash
make demo-full-corpus          # paced; Makefile sets PYTHONPATH=.
make demo-full-corpus-fast     # no pauses
PYTHONPATH=. python3 src/demo_full_corpus.py --locale en    # all sessions
PYTHONPATH=. python3 src/demo_full_corpus.py --locale ru --limit 5
```

**Factual Memory (WP-01)** is not exercised on this path; see `make demo-factual`.

## Related

- Fixtures: `e2e/fixtures/sessions/README.md`  
- Shorter integration driver: `python -m e2e` (`e2e/full_loop.py`)  
- [Issue #158](https://github.com/hleserg/atman/issues/158)
