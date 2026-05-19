# Codemap Delta Report

> Generated at 2026-05-19T14:31:42.407727+00:00 by `make codemap`. Do not edit.

**3 component(s) changed:**

### `core-ports`
- **New ports:** `DivergenceEventStore`, `EntityRegistry`, `EntityRelationExtractor`, `EntityRelationStore`, `EntityStanceStore`, `FactualMemory`, `HealthAssessmentStore`, `LinguisticAnalyzer`, `MaintenanceQueue`, `MemoryGuardian`, `MemoryReranker`, `MemoryUsageLog`, `PatternStore`, `PendingHumanReviewInbox`, `ReflectionEventStore`, `ReflectionModel`, `ReflectionOverloadAlertSink`, `ReflectionRequestQueue`, `ReflectionStore`, `SalienceDecayService`, `SelfAppliedChangeStore`, `StateStore`

### `adapters`
- **New classes:** `AtmanTurn`, `PreflightError`
- **New functions:** `check_llm`, `check_nlp_packages`, `check_postgres`, `install_nlp`, `is_warmup_needed`, `log_experience`, `run_cli_preflight`, `run_streamlit_preflight`, `start_warmup_background`

### `web-dashboard`
- **New functions:** `get_chat_deps`, `install_slog_hook`, `make_slog_hook`
