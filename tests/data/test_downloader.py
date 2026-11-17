"""Offline download tests exercise publication, HTTP errors, and path safety."""

import gzip
import os
from pathlib import Path

import pytest
import requests

from data.event_logs.downloader import download_event_log


@pytest.mark.parametrize("extension", ["xes", "csv", "CSV"])
def test_streaming_download(tmp_path, download_response, extension):
    body = b"first chunk\nsecond chunk\n"
    download_response.headers["Content-Length"] = str(len(body))
    download_response.iter_content.return_value = iter([body[:12], b"", body[12:]])
    raw_dir = tmp_path / "data" / "raw"
    url = f"https://example.org/event_log.{extension}?download=1"

    downloaded = download_event_log(url, raw_dir=raw_dir)

    assert downloaded == raw_dir / f"event_log.{extension}"
    assert downloaded.read_bytes() == body
    assert list(raw_dir.iterdir()) == [downloaded]
    requests.get.assert_called_once_with(
        url, stream=True, timeout=(10, 60), headers={"Accept-Encoding": "identity"}
    )


def test_default_raw_directory(tmp_path, monkeypatch, download_response):
    monkeypatch.chdir(tmp_path)

    path = download_event_log("http://example.org/log.xes")

    assert path.as_posix() == "data/raw/log.xes"
    assert path.read_bytes() == b"event log"


def test_url_filename_decoding(tmp_path, download_response):
    downloaded = download_event_log(
        "https://example.org/event%20log.csv?token=abc", raw_dir=tmp_path
    )
    assert downloaded.name == "event log.csv"


def test_filename_override(tmp_path, download_response):
    downloaded = download_event_log(
        "https://example.org/download?id=123", filename="receipt.xes", raw_dir=tmp_path
    )
    assert downloaded == tmp_path / "receipt.xes"


def test_existing_download_is_not_overwritten(tmp_path, download_response):
    existing = tmp_path / "log.xes"
    existing.write_bytes(b"original")

    with pytest.raises(FileExistsError, match="already exists"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path)

    assert existing.read_bytes() == b"original"
    requests.get.assert_not_called()


def test_explicit_overwrite(tmp_path, download_response):
    existing = tmp_path / "log.xes"
    existing.write_bytes(b"original")

    result = download_event_log("https://example.org/log.xes", raw_dir=tmp_path, overwrite=True)

    assert result == existing
    assert result.read_bytes() == b"event log"
    assert list(tmp_path.iterdir()) == [existing]


def test_http_error(tmp_path, download_response):
    download_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

    with pytest.raises(ValueError, match="download failed.*404"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_connection_timeout(tmp_path, download_response):
    requests.get.side_effect = requests.Timeout("connection timed out")

    with pytest.raises(ValueError, match="download failed.*timed out"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("existing", [False, True])
def test_interrupted_download_cleanup(tmp_path, download_response, existing):
    destination = tmp_path / "log.xes"
    if existing:
        destination.write_bytes(b"original")

    def interrupted_stream(**kwargs):
        yield b"partial data"
        raise requests.ConnectionError("stream interrupted")

    download_response.iter_content.side_effect = interrupted_stream
    with pytest.raises(ValueError, match="download failed.*stream interrupted"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path, overwrite=existing)

    if existing:
        assert destination.read_bytes() == b"original"
        assert list(tmp_path.iterdir()) == [destination]
    else:
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content_length", ["20", "0", "invalid", "-1"])
def test_invalid_or_incomplete_content_length(tmp_path, download_response, content_length):
    download_response.headers["Content-Length"] = content_length

    with pytest.raises(ValueError, match="Incomplete|Content-Length"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_http_compression_uses_decoded_content(tmp_path, download_response):
    download_response.headers.update({"Content-Encoding": "gzip", "Content-Length": "100"})
    # iter_content() yields decoded bytes, whose size differs from the header.
    path = download_event_log("https://example.org/log.xes", raw_dir=tmp_path)
    assert path.read_bytes() == b"event log"


def test_empty_download_is_not_published(tmp_path, download_response):
    download_response.iter_content.return_value = iter([])
    with pytest.raises(ValueError, match="empty"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("status", [204, 206, 302])
def test_incomplete_http_response(tmp_path, download_response, status):
    download_response.status_code = status
    with pytest.raises(ValueError, match="complete HTTP 200"):
        download_event_log("https://example.org/log.xes", raw_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "log.xes",
        "file:///log.xes",
        "ftp://example.org/log.xes",
        "https:///log.xes",
        "https://example.org:bad/log.xes",
        "https://example.org:99999/log.xes",
        "https://example.org:0/log.xes",
        "https://exa mple.org/log.xes",
        "\nhttps://example.org/log.xes",
    ],
)
def test_invalid_urls(tmp_path, download_response, url):
    with pytest.raises(ValueError, match="URL"):
        download_event_log(url, raw_dir=tmp_path)
    requests.get.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "filename",
    [
        "../log.csv",
        "/tmp/log.csv",
        "dir/log.csv",
        "dir\\log.csv",
        "C:log.csv",
        "",
        "..",
        ".hidden.csv",
        "bad\x00.csv",
        "bad\n.csv",
        "bad?.csv",
        "log.txt",
        "log.csv.gz",
    ],
)
def test_unsafe_or_unsupported_filenames(tmp_path, download_response, filename):
    with pytest.raises(ValueError, match="filename"):
        download_event_log("https://example.org/log.csv", filename=filename, raw_dir=tmp_path)
    requests.get.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("basename", ["..%2Flog.csv", "dir%5Clog.csv", "log.exe", ""])
def test_unsafe_url_filenames(tmp_path, download_response, basename):
    with pytest.raises(ValueError, match="filename"):
        download_event_log(f"https://example.org/{basename}", raw_dir=tmp_path)
    requests.get.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "from_url"),
    [("log.xes.gz", True), ("log.XES.GZ", True), ("renamed.xes.gz", False)],
)
def test_gzip_download_and_extraction(
    tmp_path, download_response, sample_xes, gzipped_xes, filename, from_url
):
    url = f"https://example.org/{filename}" if from_url else "https://example.org/download?id=123"
    download_response.headers["Content-Length"] = str(len(gzipped_xes))
    download_response.iter_content.return_value = iter([gzipped_xes[:16], gzipped_xes[16:]])

    result = download_event_log(url, filename=None if from_url else filename, raw_dir=tmp_path)

    archive = tmp_path / filename
    assert result == archive.with_suffix("")
    assert archive.read_bytes() == gzipped_xes
    assert result.read_bytes() == sample_xes.read_bytes()
    assert set(tmp_path.iterdir()) == {archive, result}


@pytest.mark.parametrize("existing", [("log.xes.gz",), ("log.xes",), ("log.xes.gz", "log.xes")])
def test_gzip_checks_both_destinations_before_downloading(tmp_path, download_response, existing):
    for filename in existing:
        (tmp_path / filename).write_bytes(b"original")

    with pytest.raises(FileExistsError, match="already exists"):
        download_event_log("https://example.org/log.xes.gz", raw_dir=tmp_path)

    requests.get.assert_not_called()
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        filename: b"original" for filename in existing
    }


@pytest.mark.parametrize("existing", [("log.xes.gz",), ("log.xes",), ("log.xes.gz", "log.xes")])
def test_gzip_overwrite_updates_both_files(
    tmp_path, download_response, sample_xes, gzipped_xes, existing
):
    for filename in existing:
        (tmp_path / filename).write_bytes(b"original")
    download_response.iter_content.return_value = iter([gzipped_xes])

    result = download_event_log("https://example.org/log.xes.gz", raw_dir=tmp_path, overwrite=True)

    assert result.read_bytes() == sample_xes.read_bytes()
    assert (tmp_path / "log.xes.gz").read_bytes() == gzipped_xes
    assert {path.name for path in tmp_path.iterdir()} == {"log.xes.gz", "log.xes"}


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("corruption", ["header", "truncated", "crc", "deflate", "empty"])
def test_gzip_failure_cleans_up_and_preserves_existing_files(
    tmp_path, download_response, gzipped_xes, existing, corruption
):
    if existing:
        for filename in ("log.xes.gz", "log.xes"):
            (tmp_path / filename).write_bytes(b"original")
    bodies = {
        "header": b"not a gzip file",
        "truncated": gzipped_xes[:-4],
        "crc": gzipped_xes[:-8] + bytes([gzipped_xes[-8] ^ 255]) + gzipped_xes[-7:],
        "deflate": bytes.fromhex("1f8b08000000000000ff07"),
        "empty": gzip.compress(b"", mtime=0),
    }
    body = bodies[corruption]
    download_response.headers["Content-Length"] = str(len(body))
    download_response.iter_content.return_value = iter([body])

    with pytest.raises(ValueError, match="gzip|empty"):
        download_event_log("https://example.org/log.xes.gz", raw_dir=tmp_path, overwrite=existing)

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == (
        {"log.xes.gz": b"original", "log.xes": b"original"} if existing else {}
    )


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["stream", "length"])
def test_gzip_download_failure_does_not_publish_files(
    tmp_path, download_response, gzipped_xes, existing, failure
):
    if existing:
        for filename in ("log.xes.gz", "log.xes"):
            (tmp_path / filename).write_bytes(b"original")
    if failure == "stream":

        def interrupted_stream(**kwargs):
            yield gzipped_xes[:16]
            raise requests.Timeout("read timed out")

        download_response.iter_content.side_effect = interrupted_stream
    else:
        download_response.iter_content.return_value = iter([gzipped_xes])
        download_response.headers["Content-Length"] = str(len(gzipped_xes) + 1)

    with pytest.raises(ValueError, match="download failed|Incomplete"):
        download_event_log("https://example.org/log.xes.gz", raw_dir=tmp_path, overwrite=existing)

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == (
        {"log.xes.gz": b"original", "log.xes": b"original"} if existing else {}
    )


@pytest.mark.parametrize("overwrite", [False, True])
def test_gzip_publication_failure_rolls_back_both_files(
    tmp_path, download_response, gzipped_xes, monkeypatch, overwrite
):
    if overwrite:
        for filename in ("log.xes.gz", "log.xes"):
            (tmp_path / filename).write_bytes(b"original")
    download_response.iter_content.return_value = iter([gzipped_xes])
    operation = "replace" if overwrite else "link"
    original_operation = getattr(os, operation)

    def fail_extracted_file(source, destination, *args, **kwargs):
        if Path(source).name == "log.xes" and Path(destination) == tmp_path / "log.xes":
            raise OSError("publication failed")
        return original_operation(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, operation, fail_extracted_file)

    with pytest.raises(OSError, match="publication failed"):
        download_event_log("https://example.org/log.xes.gz", raw_dir=tmp_path, overwrite=overwrite)

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == (
        {"log.xes.gz": b"original", "log.xes": b"original"} if overwrite else {}
    )
