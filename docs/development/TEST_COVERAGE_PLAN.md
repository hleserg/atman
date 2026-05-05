# Test Coverage Plan (per SYSTEM_MAP)

> Derived from [`docs/architecture/SYSTEM_MAP.md`](../architecture/SYSTEM_MAP.md)
> in response to [issue #125](https://github.com/hleserg/atman/issues/125).
>
> Each item below is a concrete test to add. Items reference the section of the
> system map they cover (§1 modules, §2 integrations, §3 scenarios A–G,
> §4 non-standard inputs, §5 known regressions). Once a test is implemented,
> mark the corresponding GAP in `SYSTEM_MAP.md` as closed and link the test
> in the PR description (per `DEVELOPMENT_STANDARD.md` §26).

---

## 1. Audit summary: what exists today

23 test files, ~230 test functions. Coverage by map section:

| Map section | Coverage | Major gap |
|---|---|---|
| §1.1 Domain models | ~85% | empty `key_moments`, empty eigenstate, very long content |
| §1.2 Ports | ~95% | — |
| §1.3 Services | ~90% | concurrency edges, decay-with-age salience |
| §1.4 Core utilities | ~85% | `reflection_run_keys` not directly tested |
| §1.5 Adapters | ~90% | malformed JSONL, `JSONDecodeError` paths |
| §1.6 CLI / TUI / Web / demos | ~20% | no CLI integration tests, no demo smoke tests |
| §2.1 Service ↔ port | ~90% | real concurrent file access |
| §2.3 CLI ↔ service | 0% | nothing |
| §2.4 Demo ↔ real objects | 0% | nothing |
| §2.5 TUI/Web ↔ subprocess | ~50% | only utils, no full app invocation |
| §2.6 Reflection chain | ~95% | — |
| §2.7 Parser ↔ model | partial | malformed JSON not exercised |
| §3 Scenarios A–G | unit-level only | no integrated end-to-end flow |
| §4.1 Empty / invalid | ~70% | empty `key_moments`, empty eigenstate, long input |
| §4.2 Duplicates | ~70% | reframing-note duplicate `triggered_by` not explicit |
| §4.3 JSON parsing | partial | malformed JSONL silent skip not asserted |
| §4.4 Governance / concurrency | ~95% | actual threading |
| §4.5 GAPs declared in map | ~30% | most GAPs still open |
| §5.1 Historical regressions | ~70% | schema migration story untested |
| §5.3 Coverage gaps | ~40% | concurrent narrative race, run-key idempotency |

---

## 2. Backlog of tests to add

### P0 — Close §4.5 GAPs and §5.3 critical regressions

| # | Test file | Test name | Asserts | Map ref |
|---|---|---|---|---|
| P0.1 | `tests/test_file_backend.py` | `test_read_facts_skips_malformed_lines_without_data_loss` | malformed JSONL line is logged via `warnings.warn` (not silent), valid lines still loaded | §4.3, §5.3 |
| P0.2 | `tests/test_file_state_store.py` | `test_get_experience_with_corrupted_json_raises_clear_error` | `json.JSONDecodeError` is wrapped or surfaced with file path context | §4.3, §5.3 |
| P0.3 | `tests/test_experience_models.py` | `test_session_experience_rejects_empty_key_moments` | `SessionExperience(key_moments=[])` → `ValueError` (or document & test that it is intentionally allowed) | §4.1, §4.5 |
| P0.4 | `tests/test_narrative_models.py` | `test_eigenstate_with_all_empty_collections_is_explicitly_marked` | empty `open_threads + dominant_themes + unresolved_tensions` either rejected or flagged | §4.1, §4.5 |
| P0.5 | `tests/test_narrative_revision.py` | `test_governance_rejected_error_is_raised_on_locked_core` | `GovernanceMode.LOCKED` on core layer update → `GovernanceRejectedError` actually raised (currently declared but never thrown) | §4.4, §5.3 |
| P0.6 | `tests/test_file_state_store.py` | `test_save_identity_concurrent_writers_either_serialize_or_conflict` | two concurrent writers: either last-write-wins is documented and tested, or `NarrativePersistenceConflictError` is raised | §4.4, §5.3 |
| P0.7 | `tests/test_reflection_services.py` | `test_reflection_run_key_idempotent_repeat_run_does_not_duplicate_snapshot` | running deep reflection twice with same `reflection_run_key` produces exactly one `IdentitySnapshot` | §4.2, §5.3 |
| P0.8 | `tests/test_file_backend.py` | `test_add_fact_duplicate_id_raises_with_clear_message` | error message includes the conflicting UUID | §4.2 |

### P1 — System-level scenarios (§3 A–G end-to-end + CLI integrations)

| # | Test file | Test name | Asserts | Map ref |
|---|---|---|---|---|
| P1.1 | `tests/test_system_e2e_lifecycle.py` (new) | `test_bootstrap_to_deep_reflection_full_lifecycle` | bootstrap identity → record 5 experiences with `FrozenClock` → micro updates recent layer → daily detects ≥1 pattern → deep produces snapshot + health → narrative markdown contains all three layers | §3 A–G |
| P1.2 | `tests/test_cli_factual_memory.py` (new) | `test_cli_add_search_link_persistence` | spawn `python -m atman.cli` via subprocess: `add` → `search --tags` → `link` → restart → records still present | §2.3, §3 F |
| P1.3 | `tests/test_cli_experience.py` (new) | `test_cli_experience_add_and_search_roundtrip` | `cli_experience add` (from fixture JSON) → `search --depth` returns it; missing fixture path produces non-zero exit | §2.3, §3 B |
| P1.4 | `tests/test_cli_identity.py` (new) | `test_cli_identity_bootstrap_render_update` | `bootstrap` → `show` → `update-value` → `show` reflects update → narrative render contains first-person text | §2.3, §3 A, §3 G |
| P1.5 | `tests/test_cli_reflection.py` (new) | `test_cli_reflection_micro_daily_deep_with_fixtures` | run all three levels via CLI on bundled fixtures; verify `ReflectionEvent` per level, no duplicate run keys on rerun | §2.3, §3 C–E |
| P1.6 | `tests/test_demo_smoke.py` (new) | `test_each_demo_module_runs_to_completion` | `python -m atman.demo`, `demo_experience_store`, `demo_identity`, `demo_reflection`, `demo_web_dashboard` exit 0; demo writes to a temp dir cleaned up afterwards | §2.4 |

### P2 — Additional unit edge cases on existing modules

| # | Test file | Test name | Asserts | Map ref |
|---|---|---|---|---|
| P2.1 | `tests/test_reflection_models.py` | `test_pattern_candidate_confidence_threshold_boundary` | `confidence=0.7` boundary behavior matches documented threshold | §1.1, §4.1 |
| P2.2 | `tests/test_experience_service.py` | `test_add_reframing_note_duplicate_triggered_by_returns_duplicate_outcome` | second note with same `triggered_by` → `ReframingNoteAppendResult.DUPLICATE_TRIGGERED_BY`, original unchanged | §4.2 |
| P2.3 | `tests/test_narrative_models.py` | `test_narrative_layer_first_person_validator_rejects_third_person_pronouns` | "the agent has learned" / "it decided" → `ValueError`; "I have learned" → ok | §1.1 |
| P2.4 | `tests/test_identity_models.py` | `test_identity_snapshot_is_frozen_against_nested_mutation` | mutating `snapshot.identity.core_values` raises or has no effect | §1.1 |
| P2.5 | `tests/test_experience_service.py` | `test_calculate_salience_decays_with_age_under_frozen_clock` | with `FrozenClock`, older `recorded_at` → strictly lower salience than identical recent record | §1.3 |
| P2.6 | `tests/test_in_memory_reflection_store.py` | `test_get_event_by_unknown_run_key_returns_none` | query for missing `run_key` returns `None` / empty list (documented behaviour) | §1.5 |
| P2.7 | `tests/test_models.py` | `test_fact_record_accepts_long_content` | content of N kB is accepted (or rejected with clear error if there is a documented cap) | §4.1 |
| P2.8 | `tests/test_tui_units.py` | `test_pytest_subprocess_nonzero_exit_surfaces_failure` | non-zero exit code → failure captured with stderr text | §2.5 |

---

## 3. Test → map section mapping (for PR descriptions)

When a PR adds tests from this backlog, it MUST cite the map section in the
"System Map" block of the PR template (per `DEVELOPMENT_STANDARD.md` §26.3):

```text
Affected map sections: §4.3, §4.5, §5.3
Tests added: tests/test_file_backend.py::test_read_facts_skips_malformed_lines_without_data_loss
GAPs closed: §4.5 — "Malformed JSONL in FileBackend (silent data loss)"
```

When the GAP in `SYSTEM_MAP.md` §4.5 / §5.3 is closed by a test, the PR also
removes the bullet from the GAP list (or marks it `done — covered by <test>`)
in **both** `SYSTEM_MAP.md` and `SYSTEM_MAP-ru.md`.

---

## 4. Suggested execution order

1. **Phase 1 — P0 (8 tests).** Closes the highest-risk gaps: data loss on
   malformed JSONL, undefined behaviour on corrupted state files, dead
   `GovernanceRejectedError` path, run-key idempotency.
2. **Phase 2 — P1 (6 tests).** Brings end-to-end coverage to the §3 scenarios
   and unblocks CLI surface (currently 0% covered).
3. **Phase 3 — P2 (8 tests).** Unit edge cases that harden existing modules.

After phase 1 the §4.5 GAP list in `SYSTEM_MAP.md` should be fully consumed.
After phase 2 every scenario in §3 has at least one e2e or CLI integration
test. After phase 3 coverage on §1 modules is uniformly ≥90% on edge cases.

---

## 5. Files touched

New files to create:

- `tests/test_system_e2e_lifecycle.py`
- `tests/test_cli_factual_memory.py`
- `tests/test_cli_experience.py`
- `tests/test_cli_identity.py`
- `tests/test_cli_reflection.py`
- `tests/test_demo_smoke.py`

Existing files to extend:

- `tests/test_file_backend.py` (P0.1, P0.8)
- `tests/test_file_state_store.py` (P0.2, P0.6)
- `tests/test_experience_models.py` (P0.3)
- `tests/test_narrative_models.py` (P0.4, P2.3)
- `tests/test_narrative_revision.py` (P0.5)
- `tests/test_reflection_services.py` (P0.7)
- `tests/test_reflection_models.py` (P2.1)
- `tests/test_experience_service.py` (P2.2, P2.5)
- `tests/test_identity_models.py` (P2.4)
- `tests/test_in_memory_reflection_store.py` (P2.6)
- `tests/test_models.py` (P2.7)
- `tests/test_tui_units.py` (P2.8)

Note: `cli.py` and `cli_experience.py` are excluded from coverage by
`pyproject.toml`. P1.2–P1.5 will require either removing the `omit` rules
for those files or accepting that the CLI integration tests improve
behaviour confidence without bumping the reported coverage number.
