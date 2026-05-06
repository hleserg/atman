# Atman components and safety / alignment relevance

Short mapping for safety reviewers, red teams, and alignment researchers: which parts of the stack touch which classes of risk or evaluation angle. This is descriptive (what the design is *for*), not a guarantee of robustness.

| Atman component | Safety / alignment relevance |
| --- | --- |
| Reality Anchor | Value drift detection in long-running agents |
| Identity Store | Stable self-model robust to contextual pressure |
| Experience Store | Honest first-hand records vs. fabricated retrospective claims |
| Reflection Engine | Metacognition; adjacent to chain-of-thought faithfulness questions |
| Jahoda framework | Multi-criterion welfare / psychological health evaluation |

For architecture detail, see [`docs/architecture/SYSTEM.md`](../architecture/SYSTEM.md). For vulnerability reporting, see [`SECURITY.md`](../../SECURITY.md).
