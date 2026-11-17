# Streaming event-log downloads

- Added `data.event_logs.downloader.download_event_log()` for HTTP(S) CSV/XES
  sources. Derive decoded URL basenames or accept a safe explicit filename;
  default storage is `data/raw/` relative to the working directory. Reject path
  components, special/control characters, hidden names, and unsupported suffixes.
- Stream with Requests and connect/read timeouts into temporary raw storage;
  publish only complete, nonempty HTTP 200 responses. Check unencoded
  Content-Length, reject partial responses, and clean up failed transfers.
  Existing files require explicit overwrite and survive failed retries.
- Declared Requests as a direct runtime dependency (already installed through
  other packages). Added shared HTTP mocks and focused downloader tests; no live
  network requests or dataset downloads are performed by tests.
- Checks: downloader tests **49 passed**, complete suite **189 passed**;
  `ruff check .` and `ruff format --check .` **passed**.
- Limitations/follow-ups: no retries/resume/archive extraction. Read timeouts
  measure inactivity, not total transfer duration. Length comparisons apply to
  unencoded bodies; encoded transfers rely on Requests' protocol error handling.
  URL-to-pipeline integration and provenance metadata are the next stage.
