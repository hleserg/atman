"""Registered product features for the developer UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoCommand:
    """One runnable demo (argv after ``uv run`` / ``python -m`` prefix)."""

    label: str
    argv: tuple[str, ...]
    env: dict[str, str]


@dataclass(frozen=True)
class FeatureInfo:
    slug: str
    title: str
    summary: str
    doc_dir: str  # relative to repo root, e.g. docs/features/foo
    related_paths: tuple[str, ...]
    demos: tuple[DemoCommand, ...]
    test_globs: tuple[str, ...]


# --- Registry literals (Sonar S1192): one definition site per repeated demo label/path/env. ---
_DEMO_LABEL_PACED = "Demo (paced)"
_DEMO_LABEL_FAST = "Demo (fast)"
_ATMAN_DEMO_PACE_ON = "1"
_ATMAN_DEMO_PACE_OFF = "off"
_DEMO_SCRIPT_FACTUAL = "src/demo.py"
_DEMO_SCRIPT_EXPERIENCE = "src/demo_experience_store.py"
_DEMO_SCRIPT_IDENTITY = "src/demo_identity.py"
_DEMO_SCRIPT_REFLECTION = "src/demo_reflection.py"
_DEMO_SCRIPT_SESSION = "src/demo_session_manager.py"
_DEMO_SCRIPT_WEB_DASHBOARD = "src/demo_web_dashboard.py"


FEATURES: tuple[FeatureInfo, ...] = (
    FeatureInfo(
        slug="factual-memory",
        title="Factual Memory Adapter",
        summary="Verifiable facts storage, search, and file-backed adapter with CLI demo.",
        doc_dir="docs/features/factual-memory",
        related_paths=(
            "src/atman/adapters/memory/",
            "src/atman/core/models/fact.py",
            "src/atman/core/ports/memory_backend.py",
            _DEMO_SCRIPT_FACTUAL,
            "src/atman/cli.py",
        ),
        demos=(
            DemoCommand(
                _DEMO_LABEL_PACED,
                (_DEMO_SCRIPT_FACTUAL,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_ON},
            ),
            DemoCommand(
                _DEMO_LABEL_FAST,
                (_DEMO_SCRIPT_FACTUAL,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_OFF},
            ),
        ),
        test_globs=(
            "tests/test_*backend*.py",
            "tests/test_models.py",
            "tests/test_file_backend.py",
        ),
    ),
    FeatureInfo(
        slug="experience-store",
        title="Experience Store",
        summary="Session experience records, salience, JSONL persistence, and service API.",
        doc_dir="docs/features/experience-store",
        related_paths=(
            "src/atman/adapters/storage/",
            "src/atman/core/models/experience.py",
            "src/atman/core/services/experience_service.py",
            _DEMO_SCRIPT_EXPERIENCE,
            "src/atman/cli_experience.py",
        ),
        demos=(
            DemoCommand(
                _DEMO_LABEL_PACED,
                (_DEMO_SCRIPT_EXPERIENCE,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_ON},
            ),
            DemoCommand(
                _DEMO_LABEL_FAST,
                (_DEMO_SCRIPT_EXPERIENCE,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_OFF},
            ),
        ),
        test_globs=(
            "tests/test_experience_*.py",
            "tests/test_experience_service.py",
        ),
    ),
    FeatureInfo(
        slug="identity-store",
        title="Identity Store",
        summary="Identity, eigenstate, self-narrative, snapshots, and CLI (WP-03).",
        doc_dir="docs/features/identity-store",
        related_paths=(
            "src/atman/core/models/identity.py",
            "src/atman/core/models/narrative.py",
            "src/atman/core/services/identity_service.py",
            "src/atman/core/services/narrative_service.py",
            "src/atman/adapters/storage/",
            _DEMO_SCRIPT_IDENTITY,
            "src/atman/cli_identity.py",
        ),
        demos=(
            DemoCommand(
                _DEMO_LABEL_PACED,
                (_DEMO_SCRIPT_IDENTITY,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_ON},
            ),
            DemoCommand(
                _DEMO_LABEL_FAST,
                (_DEMO_SCRIPT_IDENTITY,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_OFF},
            ),
        ),
        test_globs=(
            "tests/test_identity_*.py",
            "tests/test_identity_service.py",
        ),
    ),
    FeatureInfo(
        slug="reflection-engine",
        title="Reflection Engine",
        summary=(
            "Micro/daily/deep reflection, patterns, narrative revision hooks, "
            "health assessment (Jahoda), principle advisor (WP-04)."
        ),
        doc_dir="docs/features/reflection-engine",
        related_paths=(
            "src/atman/core/services/reflection_service.py",
            "src/atman/core/services/narrative_revision.py",
            "src/atman/core/services/principle_advisor.py",
            "src/atman/core/models/reflection.py",
            "src/atman/core/ports/reflection.py",
            "src/atman/adapters/reflection/",
            _DEMO_SCRIPT_REFLECTION,
            "src/atman/cli_reflection.py",
        ),
        demos=(
            DemoCommand(
                _DEMO_LABEL_PACED,
                (_DEMO_SCRIPT_REFLECTION,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_ON},
            ),
            DemoCommand(
                _DEMO_LABEL_FAST,
                (_DEMO_SCRIPT_REFLECTION,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_OFF},
            ),
        ),
        test_globs=(
            "tests/test_reflection*.py",
            "tests/test_narrative_revision.py",
            "tests/test_principle_advisor.py",
            "tests/test_mock_reflection_model.py",
            "tests/test_in_memory_reflection_store.py",
        ),
    ),
    FeatureInfo(
        slug="session-manager",
        title="Session Manager",
        summary=(
            "Session runtime that experiences sessions in real-time with first-hand "
            "emotional coloring, identity snapshots, and narrative updates (WP-05)."
        ),
        doc_dir="docs/features/session-manager",
        related_paths=(
            "src/atman/core/models/session.py",
            "src/atman/core/services/session_manager.py",
            _DEMO_SCRIPT_SESSION,
            "src/atman/core/ports/state_store.py",
        ),
        demos=(
            DemoCommand(
                _DEMO_LABEL_PACED,
                (_DEMO_SCRIPT_SESSION,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_ON},
            ),
            DemoCommand(
                _DEMO_LABEL_FAST,
                (_DEMO_SCRIPT_SESSION,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_OFF},
            ),
        ),
        test_globs=(
            "tests/test_session_manager.py",
            "tests/test_session*.py",
        ),
    ),
    FeatureInfo(
        slug="web-dashboard",
        title="Web Dashboard",
        summary="Streamlit browser UI for features, tests, and docs (same registry as TUI).",
        doc_dir="docs/features/web-dashboard",
        related_paths=(
            "src/atman/web_dashboard/app.py",
            "src/atman/web_dashboard/pages/",
            "src/atman/web_dashboard/utils/",
            _DEMO_SCRIPT_WEB_DASHBOARD,
            "Makefile",
        ),
        demos=(
            DemoCommand(
                _DEMO_LABEL_PACED,
                (_DEMO_SCRIPT_WEB_DASHBOARD,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_ON},
            ),
            DemoCommand(
                _DEMO_LABEL_FAST,
                (_DEMO_SCRIPT_WEB_DASHBOARD,),
                {"ATMAN_DEMO_PACE": _ATMAN_DEMO_PACE_OFF},
            ),
        ),
        test_globs=("tests/test_web_dashboard_*.py",),
    ),
)


def get_feature(slug: str) -> FeatureInfo | None:
    for f in FEATURES:
        if f.slug == slug:
            return f
    return None
