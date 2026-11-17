# Phase 1 documentation structure

- Replaced `docs/implementation_plan_event_logs.md` with
  `docs/event_log_preparation.md`, explaining the implemented phase rather than
  prescribing implementation stages. Added the six requested sections, a data-flow
  diagram, a local CLI example, and the handoff to Controlled Pattern Injection.
- Retained the schema, explicit UTC policy, stable source-local IDs,
  `@@source_row`, checksums, provenance groups, deterministic metadata, Parquet
  round trips, module interfaces, and testing strategy. Removed the Pandas-version
  rationale from the introduction; runtime requirements remain near architecture.
- Clarified file-pair consistency: Parquet and JSON have no shared atomic
  transaction; reload checks their association, checksum, schema, counts, and
  time range. Explained how direct column mapping and event-count validation
  avoid unintended loss from PM4Py's row-dropping formatter behavior.
- Moved detailed HTTP, filename, timeout, gzip, and publication/rollback contracts
  into `docs/event_log_downloading.md`. Updated the active README and blueprint
  references. Historical change logs retain their original file paths.
- Checks: six requested sections and nine local link targets verified;
  `ruff check .`, `ruff format --check .`, and `git diff --check` passed. Pytest
  was not run: this is a documentation-only change, as allowed by `AGENTS.md`.
- No runtime code, dependencies, datasets, prior change logs, staged changes,
  branches, or Git history were modified. No functional follow-up is required.
