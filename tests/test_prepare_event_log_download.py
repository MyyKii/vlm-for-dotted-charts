"""URL preparation uses mocked HTTP and the real event-log pipeline."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest
import requests

from data.event_logs.storage import load_processed_event_log

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_event_log.py"
CSV_MAPPINGS = [
    "--case-id-column",
    "case",
    "--activity-column",
    "activity",
    "--timestamp-column",
    "timestamp",
]


@pytest.fixture
def cli_main():
    return runpy.run_path(str(SCRIPT))["main"]


@pytest.mark.parametrize(
    "source_args",
    [[], ["--input", "log.xes", "--url", "https://example.org/log.xes"]],
)
def test_exactly_one_source_is_required(cli_main, tmp_path, capsys, source_args):
    with pytest.raises(SystemExit) as error:
        cli_main([*source_args, "--output", str(tmp_path / "log.parquet")])

    assert error.value.code == 2
    assert "--input" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_filename_requires_url(cli_main, tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        cli_main(
            [
                "--input",
                "log.xes",
                "--filename",
                "download.xes",
                "--output",
                str(tmp_path / "log.parquet"),
            ]
        )

    assert error.value.code == 2
    assert "--filename requires --url" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_help_includes_url_options(cli_main, capsys):
    with pytest.raises(SystemExit) as error:
        cli_main(["--help"])

    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--url" in help_text
    assert "--filename" in help_text


@pytest.mark.parametrize(
    ("source_format", "filename"),
    [
        ("csv", None),
        ("xes", None),
        ("csv", "renamed.csv"),
        ("xes.gz", None),
        ("xes.gz", "BPI_Challenge_2012.xes.gz"),
    ],
)
def test_url_preparation(
    cli_main,
    tmp_path,
    monkeypatch,
    capsys,
    download_response,
    sample_csv,
    sample_xes,
    gzipped_xes,
    source_format,
    filename,
):
    monkeypatch.chdir(tmp_path)
    is_gzip = source_format == "xes.gz"
    source_body = (sample_csv if source_format == "csv" else sample_xes).read_bytes()
    body = gzipped_xes if is_gzip else source_body
    download_response.headers["Content-Length"] = str(len(body))
    download_response.iter_content.return_value = iter([body[:80], body[80:]])
    url = (
        "https://example.org/download?id=log"
        if filename
        else f"https://example.org/log.{source_format}"
    )
    output = tmp_path / "processed" / "log.parquet"
    arguments = ["--url", url, "--output", str(output)]
    if source_format == "csv":
        arguments += CSV_MAPPINGS
    if filename:
        arguments += ["--filename", filename]
    if is_gzip:
        arguments += ["--dataset-id", "bpic2012"]

    assert cli_main(arguments) == 0

    downloaded = tmp_path / "data" / "raw" / (filename or f"log.{source_format}")
    assert downloaded.read_bytes() == body
    prepared_source = downloaded.with_suffix("") if is_gzip else downloaded
    assert prepared_source.read_bytes() == source_body
    metadata = json.loads(output.with_suffix(".json").read_text())
    assert metadata["source_url"] == url
    assert metadata["source_file"] == prepared_source.name
    assert metadata["source_sha256"] == hashlib.sha256(source_body).hexdigest()
    if is_gzip:
        assert metadata["dataset_id"] == "bpic2012"
        assert set(downloaded.parent.iterdir()) == {downloaded, prepared_source}
    assert metadata["num_events"] == 4
    assert metadata["num_cases"] == 2
    frame = load_processed_event_log(output)
    assert frame["identity:id"].tolist() == ["e-0", "e-1", "e-2", "e-3"]
    assert frame["org:resource"].tolist() == ["alice", "alice", "bob", "bob"]
    assert "Events: 4" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["http", "stream", "length"])
def test_download_failures_leave_no_source_or_processed_files(
    cli_main, tmp_path, monkeypatch, capsys, download_response, failure
):
    monkeypatch.chdir(tmp_path)
    if failure == "http":
        download_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    elif failure == "stream":

        def interrupted_stream(**kwargs):
            yield b"partial"
            raise requests.Timeout("read timed out")

        download_response.iter_content.side_effect = interrupted_stream
    else:
        download_response.headers["Content-Length"] = "100"
    output = tmp_path / "log.parquet"

    result = cli_main(["--url", "https://example.org/log.xes", "--output", str(output)])

    assert result == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err
    assert "Output:" not in captured.out
    assert list((tmp_path / "data" / "raw").iterdir()) == []
    assert not output.exists()
    assert not output.with_suffix(".json").exists()


def test_existing_raw_download_requires_overwrite(
    cli_main, tmp_path, monkeypatch, capsys, download_response
):
    monkeypatch.chdir(tmp_path)
    raw_file = tmp_path / "data" / "raw" / "log.xes"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"original source")
    output = tmp_path / "log.parquet"

    result = cli_main(["--url", "https://example.org/log.xes", "--output", str(output)])

    assert result == 1
    assert "already exists" in capsys.readouterr().err
    requests.get.assert_not_called()
    assert raw_file.read_bytes() == b"original source"
    assert not output.exists()


def test_overwrite_replaces_download_and_outputs(
    cli_main, tmp_path, monkeypatch, download_response, sample_csv
):
    monkeypatch.chdir(tmp_path)
    body = sample_csv.read_bytes()
    download_response.iter_content.side_effect = lambda **kwargs: iter([body])
    output = tmp_path / "log.parquet"
    arguments = ["--url", "https://example.org/log.csv", "--output", str(output), *CSV_MAPPINGS]
    assert cli_main(arguments) == 0
    original_metadata = output.with_suffix(".json").read_bytes()
    body = body.replace(b"bob", b"carol")

    assert cli_main([*arguments, "--overwrite"]) == 0

    assert (tmp_path / "data" / "raw" / "log.csv").read_bytes() == body
    metadata = json.loads(output.with_suffix(".json").read_text())
    assert metadata["source_sha256"] == hashlib.sha256(body).hexdigest()
    assert output.with_suffix(".json").read_bytes() != original_metadata
    assert "carol" in load_processed_event_log(output)["org:resource"].tolist()


def test_unsafe_cli_filename_is_rejected(
    cli_main, tmp_path, monkeypatch, capsys, download_response
):
    monkeypatch.chdir(tmp_path)

    result = cli_main(
        [
            "--url",
            "https://example.org/log.xes",
            "--filename",
            "../escape.xes",
            "--output",
            str(tmp_path / "log.parquet"),
        ]
    )

    assert result == 1
    assert "Unsafe filename" in capsys.readouterr().err
    requests.get.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_invalid_downloaded_log_keeps_complete_source(
    cli_main, tmp_path, monkeypatch, capsys, download_response
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "log.parquet"

    result = cli_main(["--url", "https://example.org/log.csv", "--output", str(output)])

    assert result == 1
    assert "Missing required columns" in capsys.readouterr().err
    assert (tmp_path / "data" / "raw" / "log.csv").read_bytes() == b"event log"
    assert not output.exists()
    assert not output.with_suffix(".json").exists()


@pytest.mark.parametrize("truncated", [False, True])
def test_invalid_gzip_cli_leaves_no_files_or_traceback(
    cli_main, tmp_path, monkeypatch, capsys, download_response, gzipped_xes, truncated
):
    monkeypatch.chdir(tmp_path)
    body = gzipped_xes[:-4] if truncated else b"not a gzip file"
    download_response.headers["Content-Length"] = str(len(body))
    download_response.iter_content.return_value = iter([body])
    output = tmp_path / "log.parquet"

    result = cli_main(["--url", "https://example.org/log.xes.gz", "--output", str(output)])

    assert result == 1
    captured = capsys.readouterr()
    assert "gzip" in captured.err
    assert "Traceback" not in captured.err
    assert "Output:" not in captured.out
    assert list((tmp_path / "data" / "raw").iterdir()) == []
    assert not output.exists()
    assert not output.with_suffix(".json").exists()
