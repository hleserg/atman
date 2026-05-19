"""Phase 2: Quality gate before docs/content/ sync.

Uses Claude API to validate content quality.
Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ContentCheckResult:
    path: str
    passed: bool
    issues: list[str]
    score: float  # 0.0..1.0


def check_content_quality(
    files: list[Path],
    min_score: float = 0.7,
) -> list[ContentCheckResult]:
    """Check quality of documentation files using Claude.

    Returns list of results. Files below min_score are flagged.
    Skips silently if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("ANTHROPIC_API_KEY not set — skipping content quality check")
        return []

    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed — skipping content quality check")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    results: list[ContentCheckResult] = []

    for path in files:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) < 100:
            # Skip tiny files
            results.append(
                ContentCheckResult(
                    path=str(path),
                    passed=True,
                    issues=[],
                    score=1.0,
                )
            )
            continue

        try:
            message = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Evaluate this documentation file for quality (completeness, clarity, "
                            f"technical accuracy). Rate 0.0-1.0 and list up to 3 issues if any.\n"
                            f'Respond as JSON: {{"score": 0.X, "issues": ["...", ...]}}\n\n'
                            f"File: {path.name}\n\n{content[:3000]}"
                        ),
                    }
                ],
            )
            import json

            resp = json.loads(message.content[0].text)  # type: ignore[index]
            score = float(resp.get("score", 0.5))
            issues = resp.get("issues", [])
        except Exception as exc:
            log.warning("Content check failed for %s: %s", path, exc)
            continue

        results.append(
            ContentCheckResult(
                path=str(path),
                passed=score >= min_score,
                issues=issues,
                score=score,
            )
        )

    return results


def check_before_sync(repo_root: Path, min_score: float = 0.7) -> bool:
    """Run content quality check on docs/content/ files before sync.

    Returns True if all files pass.
    """
    content_dir = repo_root / "docs" / "content"
    if not content_dir.exists():
        return True

    files = list(content_dir.glob("*.md"))
    results = check_content_quality(files, min_score=min_score)

    all_passed = True
    for result in results:
        if not result.passed:
            all_passed = False
            log.warning(
                "Content quality check FAILED for %s (score=%.2f): %s",
                result.path,
                result.score,
                "; ".join(result.issues),
            )

    return all_passed
