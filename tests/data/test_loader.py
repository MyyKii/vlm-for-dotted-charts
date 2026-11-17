"""Local loading preserves records, identifiers, attributes, and source files."""

import pandas as pd
import pytest

from data.event_logs import EventLogConfig
from data.event_logs.config import REQUIRED_COLUMNS
from data.event_logs.loader import load_event_log


def test_csv_loading(sample_csv):
    original = sample_csv.read_bytes()
    frame = load_event_log(
        EventLogConfig(
            sample_csv,
            case_id_column="case",
            activity_column="activity",
            timestamp_column="timestamp",
        )
    )

    assert isinstance(frame, pd.DataFrame)
    assert set(REQUIRED_COLUMNS).issubset(frame.columns)
    assert len(frame) == 4
    assert frame["case:concept:name"].tolist() == ["002", "001", "001", "002"]
    assert frame["identity:id"].tolist() == ["e-3", "e-0", "e-1", "e-2"]
    assert frame["org:resource"].tolist() == ["bob", "alice", "alice", "bob"]
    assert frame["amount"].tolist() == [5, 10, 10, 5]
    assert frame["time:timestamp"].iloc[0] == "2026-01-02T10:30:00+01:00"
    assert sample_csv.read_bytes() == original


def test_xes_loading(sample_xes):
    original = sample_xes.read_bytes()
    frame = load_event_log(EventLogConfig(sample_xes))

    assert isinstance(frame, pd.DataFrame)
    assert set(REQUIRED_COLUMNS).issubset(frame.columns)
    assert len(frame) == 4
    assert frame["case:concept:name"].tolist() == ["002", "002", "001", "001"]
    assert frame["identity:id"].tolist() == ["e-3", "e-2", "e-0", "e-1"]
    assert frame["org:resource"].tolist() == ["bob", "bob", "alice", "alice"]
    assert frame["amount"].tolist() == [5, 5, 10, 10]
    assert frame["time:timestamp"].iloc[0] == "2026-01-02T10:30:00+01:00"
    assert sample_xes.read_bytes() == original


def test_csv_separator_and_missing_values(tmp_path):
    source = tmp_path / "log.csv"
    source.write_text("case;activity;timestamp\nNA;None;\n\n", encoding="utf-8")
    frame = load_event_log(
        EventLogConfig(
            source,
            case_id_column="case",
            activity_column="activity",
            timestamp_column="timestamp",
            csv_separator=";",
        )
    )

    assert len(frame) == 2
    assert frame["case:concept:name"].tolist() == ["NA", ""]
    assert frame["concept:name"].tolist() == ["None", ""]
    assert frame["time:timestamp"].tolist() == ["", ""]


@pytest.mark.parametrize("value", ["2026-01-01T09:00:00", "not-a-date"])
def test_xes_retains_original_timestamps(sample_xes, tmp_path, value):
    source = tmp_path / "log.xes"
    source.write_text(sample_xes.read_text().replace("2026-01-01T09:00:00Z", value))

    frame = load_event_log(EventLogConfig(source))

    assert frame["time:timestamp"].tolist()[2:] == [value, value]
    assert len(frame) == 4


def test_nonexistent_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Event-log file not found"):
        load_event_log(EventLogConfig(tmp_path / "missing.csv"))


def test_directory_input(tmp_path):
    source = tmp_path / "log.csv"
    source.mkdir()
    with pytest.raises(IsADirectoryError, match="not a file"):
        load_event_log(EventLogConfig(source))


def test_unsupported_extension(tmp_path):
    with pytest.raises(ValueError, match="extension"):
        load_event_log(EventLogConfig(tmp_path / "log.txt", file_format="csv"))


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        ("csv", 'case:concept:name,concept:name,time:timestamp\n"unterminated'),
        ("csv", "case:concept:name,concept:name,time:timestamp\na,b,c,extra\n"),
        ("csv", ""),
        ("xes", "<log><trace>"),
        ("xes", "<unrelated />"),
    ],
)
def test_malformed_input(tmp_path, suffix, content):
    source = tmp_path / f"log.{suffix}"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to parse"):
        load_event_log(EventLogConfig(source))


def test_missing_columns(tmp_path):
    source = tmp_path / "log.csv"
    source.write_text("unrelated\nvalue\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required columns.*case:concept:name"):
        load_event_log(EventLogConfig(source))


def test_conflicting_column_mapping(tmp_path):
    source = tmp_path / "log.csv"
    source.write_text("case,case:concept:name,concept:name,time:timestamp\na,b,c,d\n")
    with pytest.raises(ValueError, match="would overwrite existing column"):
        load_event_log(EventLogConfig(source, case_id_column="case"))
