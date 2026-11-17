# Gzip XES usage and data contract

- Added the supplied BPIC2012 `.xes.gz` command to `README.md`, including
  `--filename`, `--output`, and `--dataset-id`. Documented retention of both raw
  files, overwrite behavior, failure cleanup, and later local use of extracted XES.
- Updated `docs/implementation_plan_event_logs.md` with supported gzip names,
  temporary streamed extraction, validation/publication rules, rollback behavior,
  and unchanged provenance semantics. General archives and compressed CSV remain
  unsupported; this extension adds no dependencies or CLI changes.
- Documentation review and final `ruff check .`, `ruff format --check .`, and
  `git diff --check` **passed**. Most recent complete suite: **229 passed**;
  downloader tests **74 passed**, URL CLI tests **18 passed**. No additional
  runtime tests were needed for this documentation-only stage.
- Verified raw `.xes.gz`/`.xes` files remain ignored by Git. Tests use mocked HTTP
  and generated small gzip bytes; the live BPIC2012 example was not downloaded.
  No research datasets, Git history, branches, or prior change logs were modified.
