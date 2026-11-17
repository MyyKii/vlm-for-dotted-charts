"""Offline CLI integration with real CSV/XES parsing and Parquet artifacts."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pm4py
import pytest
from pandas.testing import assert_frame_equal

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


def run_cli(source, output, *options):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output), *options],
        cwd=output.parent,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("source_format", ["csv", "xes"])
def test_complete_preparation(sample_csv, sample_xes, tmp_path, source_format):
    source = sample_csv if source_format == "csv" else sample_xes
    original = source.read_bytes()
    output = tmp_path / "receipt.parquet"
    mappings = CSV_MAPPINGS if source_format == "csv" else []

    result = run_cli(
        source, output, *mappings, "--dataset-id", "receipt", "--split-group-id", "receipts"
    )

    assert result.returncode == 0, result.stderr
    assert f"Input: {source}" in result.stdout
    assert "Events: 4" in result.stdout
    assert "Cases: 2" in result.stdout
    assert "Activities: 3" in result.stdout
    assert (
        "Time range (UTC): 2026-01-01T09:00:00+00:00 to 2026-01-02T09:30:00+00:00" in result.stdout
    )
    assert f"Output: {output}" in result.stdout
    assert source.read_bytes() == original
    metadata = json.loads(output.with_suffix(".json").read_text())
    assert metadata["dataset_id"] == "receipt"
    assert metadata["split_group_id"] == "receipts"
    assert metadata["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert metadata["num_events"] == 4
    assert metadata["num_cases"] == 2
    frame = load_processed_event_log(output)
    assert frame["identity:id"].tolist() == ["e-0", "e-1", "e-2", "e-3"]
    assert frame["org:resource"].tolist() == ["alice", "alice", "bob", "bob"]
    formatted = pm4py.format_dataframe(frame.copy())
    assert len(formatted) == len(frame)
    assert formatted["identity:id"].tolist() == frame["identity:id"].tolist()
    log = pm4py.convert_to_event_log(frame)
    assert len(log) == 2
    assert sum(len(trace) for trace in log) == 4


def test_deterministic_cli_and_overwrite_protection(sample_csv, tmp_path):
    output = tmp_path / "log.parquet"
    first = run_cli(sample_csv, output, *CSV_MAPPINGS)
    assert first.returncode == 0, first.stderr
    data_before = output.read_bytes()
    metadata_before = output.with_suffix(".json").read_bytes()
    frame_before = load_processed_event_log(output)

    refused = run_cli(sample_csv, output, *CSV_MAPPINGS)
    assert refused.returncode != 0
    assert "already exists" in refused.stderr
    assert "Output:" not in refused.stdout
    assert output.read_bytes() == data_before
    assert output.with_suffix(".json").read_bytes() == metadata_before

    repeated = run_cli(sample_csv, output, *CSV_MAPPINGS, "--overwrite")
    assert repeated.returncode == 0, repeated.stderr
    assert output.read_bytes() == data_before
    assert output.with_suffix(".json").read_bytes() == metadata_before
    assert_frame_equal(frame_before, load_processed_event_log(output))


@pytest.mark.parametrize(
    ("timestamp", "date_format", "expected"),
    [
        ("02.01.2026 12:30", "%d.%m.%Y %H:%M", "2026-01-02T11:30:00+00:00"),
        ("01022026", "%d%m%Y", "2026-01-31T23:00:00+00:00"),
    ],
)
def test_csv_format_and_timezone_configuration(tmp_path, timestamp, date_format, expected):
    source = tmp_path / "log.csv"
    source.write_text(f"case;activity;timestamp\n001;Start;{timestamp}\n", encoding="utf-8")
    output = tmp_path / "log.parquet"

    result = run_cli(
        source,
        output,
        *CSV_MAPPINGS,
        "--csv-separator",
        ";",
        "--timestamp-format",
        date_format,
        "--source-timezone",
        "Europe/Berlin",
    )

    assert result.returncode == 0, result.stderr
    frame = load_processed_event_log(output)
    assert frame["case:concept:name"].tolist() == ["001"]
    assert frame["identity:id"].tolist() == ["source-row:0"]
    assert frame["time:timestamp"].iloc[0].isoformat() == expected
    assert "Diagnostic: All events share the same timestamp" in result.stderr


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("case,activity,timestamp\na,Start,invalid\n", "time:timestamp"),
        ("case,activity,timestamp\na,Start,2026-01-01T12:00:00\n", "requires source_timezone"),
        ("case,activity,timestamp\n,Start,2026-01-01T12:00:00Z\n", "case:concept:name"),
        ("case,activity,timestamp\na,,2026-01-01T12:00:00Z\n", "concept:name"),
        ("case,activity,timestamp\n", "empty"),
    ],
)
def test_invalid_inputs_leave_no_processed_files(tmp_path, content, error):
    source = tmp_path / "invalid.csv"
    source.write_text(content, encoding="utf-8")
    output = tmp_path / "log.parquet"

    result = run_cli(source, output, *CSV_MAPPINGS)

    assert result.returncode != 0
    assert error in result.stderr
    assert "Traceback" not in result.stderr
    assert "Output:" not in result.stdout
    assert not output.exists()
    assert not output.with_suffix(".json").exists()


def test_xes_naive_timestamps_require_configuration(sample_xes, tmp_path):
    source = tmp_path / "naive.xes"
    source.write_text(sample_xes.read_text().replace("2026-01-01T09:00:00Z", "2026-01-01T09:00:00"))
    output = tmp_path / "log.parquet"

    refused = run_cli(source, output)
    assert refused.returncode != 0
    assert "requires source_timezone" in refused.stderr
    assert not output.exists()

    accepted = run_cli(source, output, "--source-timezone", "Europe/Berlin")
    assert accepted.returncode == 0, accepted.stderr
    frame = load_processed_event_log(output)
    assert frame["time:timestamp"].iloc[0].isoformat() == "2026-01-01T08:00:00+00:00"


def test_missing_file(tmp_path):
    result = run_cli(tmp_path / "missing.xes", tmp_path / "log.parquet")
    assert result.returncode != 0
    assert "file not found" in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("timestamp", ["2026-10-25T02:30:00", "2026-03-29T02:30:00"])
def test_dst_errors_have_no_traceback_or_output(tmp_path, timestamp):
    source = tmp_path / "log.csv"
    source.write_text(f"case,activity,timestamp\na,Start,{timestamp}\n", encoding="utf-8")
    output = tmp_path / "log.parquet"

    result = run_cli(source, output, *CSV_MAPPINGS, "--source-timezone", "Europe/Berlin")

    assert result.returncode != 0
    assert "time:timestamp" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
    assert not output.with_suffix(".json").exists()


def test_duplicate_events_are_retained(tmp_path):
    source = tmp_path / "log.csv"
    source.write_text(
        "case,activity,timestamp\n" + "a,Start,2026-01-01T12:00:00Z\n" * 2, encoding="utf-8"
    )
    output = tmp_path / "log.parquet"

    result = run_cli(source, output, *CSV_MAPPINGS)

    assert result.returncode == 0, result.stderr
    assert "Duplicate case/activity/timestamp combinations: 1" in result.stderr
    frame = load_processed_event_log(output)
    assert len(frame) == 2
    assert frame["identity:id"].tolist() == ["source-row:0", "source-row:1"]
