# Event-log configuration and setup

- Added the `data.event_logs` package and immutable `EventLogConfig` with standard
  columns, format inference, CSV settings, and explicit timestamp/timezone options.
  Invalid paths, formats, mappings, separators, and timezone names fail early.
- Added `tests/data/test_config.py` and the staged implementation document.
  Runtime dependencies already included PM4Py, Pandas, and PyArrow; no dependency
  changes were necessary. Installed the project and dev group in editable mode.
- Fixed pre-existing Ruff formatting in `tests/test_smoke.py` and one Python
  example in `docs/blueprint.md` so the required repository-wide check passes.
- Checks: configuration tests **29 passed**; complete suite **39 passed**;
  `ruff check .` and `ruff format --check .` **passed**. An isolated Python import
  verified the editable installation. Initial sandboxed installation failed on
  network resolution; the authorized network-enabled retry succeeded.
- Follow-ups: loading, preprocessing/validation, Parquet storage, and CLI remain
  subsequent stages. Configuration does not access or modify source files.
