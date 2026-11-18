# Efficient batching feasibility and modifying assignments

- Replaced repeated candidate-by-candidate table scans in `engine.py` with one
  boundary sweep over eligible predecessor/successor windows. It counts distinct
  cases and possible modifications, then filters at the chosen center once.
  Candidate shuffling and local seeded randomness remain deterministic; grouped
  event choices replace per-case scans. No scheduling framework was introduced.
- Automatic selection prefers modifying cases/events and skips entirely no-op
  centers. Jitter excludes an event's original timestamp when another feasible
  value exists. Explicit IDs are preserved; forced unchanged events remain when
  needed for the requested batch size. Explicit no-op injections still fail.
- Added regressions for 10,000 cases / 30,000 events with disjoint eligible
  windows, bounded scan counts, reproducible alternative centers, modifying
  choices within/across cases, required forced no-ops, and nanosecond jitter.
  Updated `docs/pattern_injection.md` with the implemented policy.
- Checks: focused batching/integrity tests **83 passed**; focused Ruff lint
  **passed**. Formatting was applied only to affected files. Full-project checks
  follow after blueprint alignment.
- Constraints remain: one selected event per distinct case, chronological/source
  tie order, exact immediate changes, conflict rejection, and final regions.
  Avoiding no-ops can change earlier seeded assignments; effective choices remain
  recorded. No CLI, Phase-1, dependency, rendering, or artifact-layout changes.
