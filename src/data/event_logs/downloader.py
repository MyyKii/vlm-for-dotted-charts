"""Stream HTTP(S) event logs into raw storage without publishing partial files."""

import gzip
import os
import re
import shutil
import zlib
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit

import requests


def _publish_files(files: list[Path], directory: Path, *, overwrite: bool) -> None:
    """Publish complete files, rolling back changes if any publication fails."""
    with ExitStack() as rollback:
        for index, staged in enumerate(files):
            destination = directory / staged.name
            had_previous = overwrite and (destination.exists() or destination.is_symlink())
            if had_previous:
                backup = staged.parent / f".previous-{index}"
                os.link(destination, backup, follow_symlinks=False)
                rollback.callback(os.replace, backup, destination)
            if overwrite:
                os.replace(staged, destination)
            else:
                os.link(staged, destination)
            if not had_previous:
                rollback.callback(destination.unlink, missing_ok=True)
        rollback.pop_all()


def download_event_log(
    url: str,
    *,
    filename: str | None = None,
    raw_dir: Path | str = Path("data/raw"),
    overwrite: bool = False,
) -> Path:
    """Download a CSV/XES source; extract .xes.gz and return the .xes path.

    Use the decoded URL basename unless ``filename`` overrides it. Filenames
    must start with a letter, number, or underscore and contain only word
    characters, spaces, dots, and hyphens. Never interpret directory components.
    Stream with 10-second connect and 60-second read-inactivity timeouts. Check
    Content-Length when supplied for an unencoded response; HTTP compression is
    decoded by Requests. Publish only a complete, nonempty response. Existing
    files are retained unless overwrite is explicit, including on failed retries.
    For .xes.gz, stage and verify decompression before publishing both the original
    archive and nonempty extracted XES. Check overwrite permission for both paths.
    """
    if not isinstance(url, str) or not url or any(char.isspace() or ord(char) < 32 for char in url):
        raise ValueError("URL must be a valid HTTP(S) URL without whitespace or control characters")
    try:
        parsed = urlsplit(url)
        port = parsed.port  # Access validates malformed/out-of-range ports.
    except ValueError as error:
        raise ValueError(f"Invalid HTTP(S) URL: {error}") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or port == 0:
        raise ValueError("URL must use HTTP(S) and include a valid host")
    name = unquote(parsed.path.rsplit("/", 1)[-1]) if filename is None else filename
    if not isinstance(name, str) or not re.fullmatch(r"\w[\w .-]*", name):
        raise ValueError("Unsafe filename: use a basename without paths or special characters")
    is_gzip = name.lower().endswith(".xes.gz")
    if Path(name).suffix.lower() not in {".xes", ".csv"} and not is_gzip:
        raise ValueError("Download filename must end with .xes, .csv, or .xes.gz; use --filename")

    directory = Path(raw_dir)
    destination = directory / name
    destinations = [destination, destination.with_suffix("")] if is_gzip else [destination]
    for path in destinations:
        if (path.exists() or path.is_symlink()) and not overwrite:
            raise FileExistsError(f"Download already exists: {path}; explicitly allow overwrite")
    directory.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(
            url, stream=True, timeout=(10, 60), headers={"Accept-Encoding": "identity"}
        ) as response:
            response.raise_for_status()
            if response.status_code != 200 or "Content-Range" in response.headers:
                raise ValueError("Download requires a complete HTTP 200 response")
            expected_size = None
            if (
                "Content-Length" in response.headers
                and response.headers.get("Content-Encoding", "identity").lower() == "identity"
            ):
                try:
                    expected_size = int(response.headers["Content-Length"])
                except ValueError as error:
                    raise ValueError("Invalid download Content-Length") from error
                if expected_size < 0:
                    raise ValueError("Invalid download Content-Length")
            with TemporaryDirectory(prefix=f".{name}-", dir=directory) as temporary:
                staged = Path(temporary) / name
                size = 0
                with staged.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            output.write(chunk)
                            size += len(chunk)
                if size == 0 or (expected_size is not None and size != expected_size):
                    raise ValueError("Incomplete or empty event-log download")
                files = [staged]
                if is_gzip:
                    extracted = staged.with_suffix("")
                    try:
                        with gzip.open(staged, "rb") as source, extracted.open("wb") as output:
                            shutil.copyfileobj(source, output, length=64 * 1024)
                    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
                        raise ValueError(
                            f"Unable to decompress gzip XES file {name!r}: {error}"
                        ) from error
                    if extracted.stat().st_size == 0:
                        raise ValueError("Extracted XES file is empty")
                    files.append(extracted)
                _publish_files(files, directory, overwrite=overwrite)
    except requests.RequestException as error:
        raise ValueError(f"Event-log download failed: {error}") from error
    return destinations[-1]
