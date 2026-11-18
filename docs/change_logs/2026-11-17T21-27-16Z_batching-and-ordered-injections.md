# Phase 2 stage 3 — batching and ordered injections

- Implemented `synchronize_events` and feasible target resolution with the
  user-confirmed policy: at most one event per distinct case, seeded selection
  when targets are omitted, uniform jitter within center ± jitter, and rejection
  of infeasible targets. Timestamp assignments also respect predecessor/successor
  bounds and original source-row tie order. Precise resolved assignments and
  case/activity selections are saved; regions are instants or intervals including
  the latest selected event. Precision increases only when assignments require it.
- Enabled ordered recipes, distinct injection IDs/change filters, immediate
  pre/post records, and independently validated final regions. Later targets
  containing changed events are rejected; disjoint edits that invalidate earlier
  locations also fail. No conflict repair or reordering is performed.
- Updated `engine.py`, `patterns.py`, focused batching/recipe tests, and
  `docs/pattern_injection.md`. Explicitly documented selected-but-unchanged batch
  events and their absence from the exact changes table.
- Checks: focused Phase-2 suite **74 passed**; Ruff lint and formatting checks on
  affected Python files **passed**. Initial jitter tests exposed a microsecond/
  nanosecond assignment issue, fixed and retested without warnings. Cases include
  disjoint mixed recipes, separate batch instances, overlapping targets, gap
  invalidation, deterministic targeting, tie order, and ordered reconstruction.
- Limitations/follow-ups: stage 4 completes direct batching CLI flags, broader
  integration/schema checks, README, and full-project verification. Remaining
  candidate classes and all rendering/annotation/training remain out of scope.
