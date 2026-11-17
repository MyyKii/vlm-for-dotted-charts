# URL input argument selection

- Added mutually exclusive, required `--input`/`--url` options and optional
  `--filename` to `scripts/prepare_event_log.py`. A filename override requires URL
  input. Existing preparation options and local-file execution remain unchanged.
- Added four argument/help tests in `tests/test_prepare_event_log_download.py`.
- Checks: focused tests **4 passed**, complete suite **140 passed**;
  `ruff check .` and `ruff format --check .` **passed**.
- Follow-up: this stage defines the CLI interface. The streaming downloader and
  URL execution/provenance integration are the next stages; URL preparation is
  not yet complete. No network requests or dataset downloads were performed.
