# URL preparation and source provenance

- Connected CLI URL inputs to `download_event_log()` before building the existing
  configuration. The same loader, preprocessor, validator, and storage functions
  prepare both local and downloaded files. `--overwrite` applies to the download
  and processed artifacts; summaries identify the actual local source path.
- Added optional `source_url` to `save_processed_event_log()`. URL metadata retains
  the original URL alongside the local `source_file`, `source_sha256`, and
  checksum-based `source_id`. Local calls omit the new field, preserving their
  existing metadata. No changes to loading, preprocessing, or validation behavior.
- Added mocked HTTP CLI integration tests for XES/CSV, filename overrides,
  overwrite behavior, HTTP/stream/length failures, path safety, complete-but-invalid
  logs, and provenance. Added a storage URL/checksum test and local metadata
  regression assertion. Completed downloads remain unchanged even if subsequent
  log validation fails; failed downloads leave no incomplete raw files.
- Checks: focused CLI/storage tests **36 passed**, complete suite **200 passed**;
  `ruff check .`, `ruff format --check .`, and `git diff --check` **passed**.
- Follow-up: README/technical contract updates and final verification. Tests are
  offline and CPU-only; HTTP calls are mocked and no real datasets were fetched.
