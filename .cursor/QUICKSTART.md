# Quick Start for Local Agents

> **For local Cursor agents working on the Atman project**

## Before You Start Any Work

**Read these 3 files in order:**

1. 📋 [`local-agent-master-prompt.md`](local-agent-master-prompt.md) — Your primary workflow guide
2. 📖 [`../docs/development/DEVELOPMENT_STANDARD.md`](../docs/development/DEVELOPMENT_STANDARD.md) — Complete development standard
3. 🏗️ [`../docs/architecture/SYSTEM.md`](../docs/architecture/SYSTEM.md) — System architecture

## Essential Rules

- Use **canonical terms** only (Fact, Experience, Identity, Narrative, etc.)
- Never mix domain concepts (Fact ≠ Experience ≠ Reflection)
- Core code must be independent of adapters (mem0, OpenClaw, specific LLMs)
- Every persistent structure needs `schema_version`
- English docs first, then sync Russian versions for key files
- Must run locally without external services

## Quick Reference

```bash
# Project structure
/workspace/
├── .cursor/                 # ← Local agent instructions (YOU ARE HERE)
├── docs/development/        # ← Development standards
├── docs/architecture/       # ← System design
├── src/atman/              # ← Implementation
└── tests/                  # ← Test suite

# Commands
pip install -e .[dev]       # Install dependencies (including dev/test)
pytest tests/ -v            # Run tests
python3 -m atman.cli        # Interactive CLI
```

## Definition of Done

Before finishing work, verify:

- [ ] Uses canonical terminology
- [ ] Does not mix domain concepts
- [ ] Has explicit ports/adapters (if touching Core)
- [ ] Runs locally without external services
- [ ] Has tests for core invariants
- [ ] Documents runtime commands
- [ ] Describes persistent data with schema versions

## Need More Details?

- **Workflow & Standards** → [`local-agent-master-prompt.md`](local-agent-master-prompt.md)
- **Terminology & Architecture** → [`../docs/development/DEVELOPMENT_STANDARD.md`](../docs/development/DEVELOPMENT_STANDARD.md)
- **Component Design** → [`../docs/architecture/SYSTEM.md`](../docs/architecture/SYSTEM.md)
- **Sync Process** → [`SYNC_GUIDE.md`](SYNC_GUIDE.md)

---

**Remember**: You're not just following rules — you're maintaining the integrity of Atman's architecture. Every component must speak the same language.
