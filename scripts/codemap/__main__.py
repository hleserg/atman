"""Living Codemap CLI entry point.

Usage:
    python -m scripts.codemap --no-coverage --lang en           # main run
    python -m scripts.codemap --lang en --check                  # CI check mode
    python -m scripts.codemap readme --lang en                   # update README.md markers
    python -m scripts.codemap agents --lang en                   # update AGENTS.md + .cursor/rules
    python -m scripts.codemap flag-stale-ru                      # mark RU blocks needing translation
    python -m scripts.codemap translate --lang ru --only-stale   # Phase 2: translate stale RU
    python -m scripts.codemap docs-fix                           # apply HIGH-confidence doc moves
    python -m scripts.codemap docs-fix --dry-run                 # preview moves
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure repo root is importable when run as python -m scripts.codemap
_REPO_ROOT = Path(__file__).parent.parent.parent


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(levelname)s  %(name)s  %(message)s",
        level=level,
    )


def _load_components(_repo_root: Path) -> dict:
    try:
        import yaml
    except ImportError:
        logging.error("pyyaml not available. pip install pyyaml")
        return {}

    cfg_path = Path(__file__).parent / "components.yaml"
    if not cfg_path.exists():
        logging.error("components.yaml not found at %s", cfg_path)
        return {}

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return data.get("components", {})


def _run_main(args: argparse.Namespace, repo_root: Path) -> int:
    """Run the full codemap update pipeline."""
    from .extractor.ast_walker import walk_directory
    from .renderer.delta import write_delta_report
    from .renderer.endpoints import write_endpoints
    from .renderer.startup_deps import write_startup_deps
    from .renderer.system_map import update_system_map
    from .renderer.test_env import write_test_env
    from .renderer.undocumented import write_undocumented
    from .snapshot.diff import diff_snapshots
    from .snapshot.store import ComponentSnapshot, load_snapshot, save_snapshot

    check_mode = args.check
    components = _load_components(repo_root)

    if not components:
        logging.error("No components defined in components.yaml")
        return 1

    run_ts = datetime.now(tz=UTC).isoformat()
    any_stale = False

    # --- 1. Walk all components and build snapshots ---
    diffs = []
    component_files: dict = {}
    for comp_id, cfg in components.items():
        path = repo_root / cfg["path"]
        files = walk_directory(path)
        component_files[comp_id] = files

        # Build snapshot
        all_classes = [c.name for fm in files for c in fm.public_classes]
        all_fns = [f.name for fm in files for f in fm.public_functions]
        all_ports = [p.name for fm in files for p in fm.ports]
        all_pydantic = [m for fm in files for m in fm.pydantic_models]
        all_cli = [c for fm in files for c in fm.cli_commands]
        all_todos = sum(len(fm.todos) for fm in files)
        all_schemas = [v for fm in files for v in fm.schema_versions]

        new_snap = ComponentSnapshot(
            component_id=comp_id,
            recorded_at=run_ts,
            class_names=all_classes,
            function_names=all_fns,
            port_names=all_ports,
            pydantic_model_names=all_pydantic,
            cli_commands=all_cli,
            todo_count=all_todos,
            file_count=len(files),
            schema_versions=all_schemas,
        )
        old_snap = load_snapshot(comp_id, base=repo_root / ".codemap/snapshots")
        diff = diff_snapshots(old_snap, new_snap)
        diffs.append(diff)

        if not check_mode:
            save_snapshot(new_snap, base=repo_root / ".codemap/snapshots")

    # --- 2. Update SYSTEM_MAP.md ---
    system_map = repo_root / "docs" / "architecture" / "SYSTEM_MAP.md"
    if system_map.exists():
        changed = update_system_map(system_map, repo_root, components, check_mode=check_mode)
        if changed:
            any_stale = True
            if check_mode:
                logging.warning("SYSTEM_MAP.md has stale codemap blocks")
    else:
        logging.info("SYSTEM_MAP.md not found — skipping system map update")

    # --- 3. Write ancillary reports ---
    if not check_mode:
        write_startup_deps(repo_root)
        write_test_env(repo_root)
        write_endpoints(repo_root, component_files)
        write_undocumented(component_files, repo_root)
        write_delta_report(diffs, run_ts, repo_root)

    # --- 4. Coverage (unless --no-coverage) ---
    if not getattr(args, "no_coverage", False) and not check_mode:
        _run_coverage_report(repo_root)

    logging.info("Codemap run complete. Timestamp: %s", run_ts)

    if check_mode and any_stale:
        logging.error("One or more codemap blocks are stale. Run `make codemap` to update.")
        return 1
    return 0


def _run_coverage_report(repo_root: Path) -> None:
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--co", "-q", "--no-header"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=30,
        )
        lines = result.stdout.splitlines()
        test_count = sum(1 for ln in lines if ln.startswith("tests/") or "<Module" in ln)
        logging.info("Test discovery: ~%d items found", test_count)
    except Exception as exc:
        logging.debug("Coverage check skipped: %s", exc)


def _cmd_readme(args: argparse.Namespace, repo_root: Path) -> int:
    from .renderer.readme import update_readme

    components = _load_components(repo_root)
    changed = update_readme(
        repo_root / "README.md",
        repo_root,
        components,
        check_mode=args.check,
    )
    if args.check and changed:
        logging.error("README.md has stale codemap blocks")
        return 1
    return 0


def _cmd_agents(args: argparse.Namespace, repo_root: Path) -> int:
    from .agent_instructions import update_agent_instructions

    changed = update_agent_instructions(
        repo_root,
        check_mode=args.check,
        lang=args.lang,
    )
    if args.check and changed:
        logging.error("Agent instruction files have stale codemap blocks")
        return 1
    return 0


def _cmd_flag_stale_ru(_args: argparse.Namespace, repo_root: Path) -> int:
    from .renderer.i18n import flag_stale_ru_blocks
    from .snapshot.en_hashes import HASHES_FILE

    pairs = [
        (
            repo_root / "docs/architecture/SYSTEM_MAP.md",
            repo_root / "docs/architecture/SYSTEM_MAP-ru.md",
        ),
        (repo_root / "README.md", repo_root / "README-ru.md"),
    ]
    any_stale = False
    hashes_path = repo_root / HASHES_FILE

    for en_path, ru_path in pairs:
        stale = flag_stale_ru_blocks(en_path, ru_path, hashes_path)
        if stale:
            any_stale = True
            logging.info("Stale RU sections in %s: %s", ru_path, stale)

    if not any_stale:
        logging.info("All RU blocks are up to date")
    return 0


def _cmd_translate(args: argparse.Namespace, repo_root: Path) -> int:
    from .snapshot.en_hashes import HASHES_FILE
    from .translator import translate_stale_blocks

    pairs = [
        (
            repo_root / "docs/architecture/SYSTEM_MAP.md",
            repo_root / "docs/architecture/SYSTEM_MAP-ru.md",
        ),
        (repo_root / "README.md", repo_root / "README-ru.md"),
    ]
    hashes_path = repo_root / HASHES_FILE
    only_stale = getattr(args, "only_stale", True)

    for en_path, ru_path in pairs:
        translated = translate_stale_blocks(
            en_path, ru_path, only_stale=only_stale, hashes_file=hashes_path
        )
        if translated:
            logging.info("Translated %d sections in %s", len(translated), ru_path)

    return 0


def _cmd_docs_fix(args: argparse.Namespace, repo_root: Path) -> int:
    from .classifier import apply_high_confidence_moves, classify_docs, write_misplaced_json

    dry_run = getattr(args, "dry_run", False)
    misplaced = classify_docs(repo_root)
    write_misplaced_json(misplaced, repo_root)

    if not misplaced:
        logging.info("No misplaced docs found")
        return 0

    logging.info("Found %d potentially misplaced docs", len(misplaced))
    moves = apply_high_confidence_moves(misplaced, repo_root, dry_run=dry_run)

    if dry_run:
        for src, dst in moves:
            print(f"  WOULD MOVE: {src}  →  {dst}")
    else:
        for src, dst in moves:
            logging.info("Moved: %s → %s", src, dst)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.codemap",
        description="Living Codemap — auto-documentation generator for Atman",
    )
    parser.add_argument("--lang", default="en", choices=["en", "ru"], help="Language")
    parser.add_argument("--check", action="store_true", help="CI check mode: exit 1 if stale")
    parser.add_argument(
        "--no-coverage", action="store_true", dest="no_coverage", help="Skip coverage check"
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    subparsers = parser.add_subparsers(dest="command")

    # readme subcommand
    readme_p = subparsers.add_parser("readme", help="Update README.md codemap markers")
    readme_p.add_argument("--lang", default="en", choices=["en", "ru"])
    readme_p.add_argument("--check", action="store_true")

    # agents subcommand
    agents_p = subparsers.add_parser("agents", help="Update AGENTS.md and .cursor/rules")
    agents_p.add_argument("--lang", default="en", choices=["en", "ru"])
    agents_p.add_argument("--check", action="store_true")

    # flag-stale-ru subcommand
    subparsers.add_parser("flag-stale-ru", help="Report stale RU blocks")

    # translate subcommand
    translate_p = subparsers.add_parser("translate", help="Phase 2: translate stale RU blocks")
    translate_p.add_argument("--lang", default="ru", choices=["ru"])
    translate_p.add_argument("--only-stale", action="store_true", dest="only_stale", default=False)

    # docs-fix subcommand
    docsfix_p = subparsers.add_parser("docs-fix", help="Move misplaced docs")
    docsfix_p.add_argument("--dry-run", action="store_true", dest="dry_run")

    args = parser.parse_args()
    _setup_logging(getattr(args, "verbose", False))

    repo_root = _REPO_ROOT.resolve()
    logging.debug("Repo root: %s", repo_root)

    cmd = getattr(args, "command", None)

    if cmd == "readme":
        return _cmd_readme(args, repo_root)
    elif cmd == "agents":
        return _cmd_agents(args, repo_root)
    elif cmd == "flag-stale-ru":
        return _cmd_flag_stale_ru(args, repo_root)
    elif cmd == "translate":
        return _cmd_translate(args, repo_root)
    elif cmd == "docs-fix":
        return _cmd_docs_fix(args, repo_root)
    else:
        # Default: full run
        return _run_main(args, repo_root)


if __name__ == "__main__":
    sys.exit(main())
