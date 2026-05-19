# Sentry Setup

> **Russian version:** [SENTRY_SETUP-ru.md](SENTRY_SETUP-ru.md)

## Overview

Sentry integration in Atman is entirely opt-in. When `SENTRY_DSN` is not set, the observability module is a complete no-op — no SDK is loaded, no network calls are made, and there is zero runtime cost.

The integration is located in `src/atman/adapters/observability/sentry.py`.

## Configuration

Set the `SENTRY_DSN` environment variable to enable Sentry:

```bash
SENTRY_DSN=https://<key>@sentry.io/<project-id>
```

Additional optional variables:

```bash
# Environment tag shown in Sentry (dev | routine | ci)
SENTRY_ENVIRONMENT=dev

# Fraction of transactions to record for performance monitoring (0.0–1.0)
SENTRY_TRACES_SAMPLE_RATE=0.1
```

## What Is Tracked

When Sentry is enabled, the adapter captures:

| Signal | Details |
|--------|---------|
| **Errors** | Unhandled exceptions from all Atman components |
| **Routine spans** | Periodic maintenance and background job execution |
| **Translation failures** | Errors when converting between domain models and adapter representations |
| **Session transactions** | Full session lifecycle from `start_session` to `finish_session` |
| **Maintenance spans** | Individual maintenance job execution (claim → dispatch → complete) |

## Environments

Use `SENTRY_ENVIRONMENT` to tag events with the context they come from:

| Value | When to use |
|-------|-------------|
| `dev` | Local development and manual testing |
| `routine` | Scheduled background tasks (daily reflection, maintenance) |
| `ci` | Automated tests in CI pipelines |

Setting different environments lets you filter noise in the Sentry UI — for example, exclude `ci` events from production dashboards.

## How to View

1. Open your Sentry project at [sentry.io](https://sentry.io).
2. Navigate to **Issues** to see errors grouped by type.
3. Navigate to **Performance** to see transaction traces.
4. Use the **Environment** filter to switch between `dev`, `routine`, and `ci`.

## SDK Version

Atman requires `sentry-sdk >= 2.35.0`. This version is listed as an optional dependency and is installed automatically when using the `sentry` extras:

```bash
pip install "atman[sentry]"
```

Or install manually:

```bash
pip install "sentry-sdk>=2.35.0"
```

If the SDK is not installed and `SENTRY_DSN` is set, Atman will log a warning at startup but continue running normally.
