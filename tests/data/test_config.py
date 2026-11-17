"""Configuration validation does not depend on a real event log."""

from pathlib import Path

import pytest

from data.event_logs import EventLogConfig


def test_defaults():
    config = EventLogConfig("data/raw/receipt.xes")

    assert config.input_path == Path("data/raw/receipt.xes")
    assert config.file_format == "xes"
    assert config.case_id_column == "case:concept:name"
    assert config.activity_column == "concept:name"
    assert config.timestamp_column == "time:timestamp"
    assert config.csv_separator == ","
    assert config.timestamp_format is None
    assert config.source_timezone is None


@pytest.mark.parametrize("file_format", ["xes", "csv", "XES", "CSV"])
def test_supported_formats(file_format):
    config = EventLogConfig(Path("source") / f"log.{file_format}", file_format=file_format)

    assert config.file_format == file_format.lower()


def test_csv_settings():
    config = EventLogConfig(
        "log.csv",
        case_id_column="case",
        activity_column="activity",
        timestamp_column="timestamp",
        csv_separator=";",
        timestamp_format="%d.%m.%Y %H:%M",
        source_timezone="Europe/Berlin",
    )

    assert config.csv_separator == ";"
    assert config.source_timezone == "Europe/Berlin"
    assert config.timestamp_format == "%d.%m.%Y %H:%M"


def test_missing_input_path():
    with pytest.raises(TypeError, match="input_path"):
        EventLogConfig()


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"input_path": ""}, "input_path"),
        ({"input_path": "   "}, "input_path"),
        ({"input_path": None}, "input_path"),
        ({"input_path": 42}, "input_path"),
        ({"input_path": Path("/")}, "input_path"),
        ({"input_path": "log.json"}, "file_format"),
        ({"file_format": "json"}, "file_format"),
        ({"file_format": ""}, "file_format"),
        ({"file_format": 42}, "file_format"),
        ({"case_id_column": ""}, "case_id_column"),
        ({"activity_column": " "}, "activity_column"),
        ({"timestamp_column": None}, "timestamp_column"),
        ({"activity_column": "case:concept:name"}, "distinct"),
        ({"csv_separator": ""}, "csv_separator"),
        ({"csv_separator": "||"}, "csv_separator"),
        ({"csv_separator": "\n"}, "csv_separator"),
        ({"csv_separator": None}, "csv_separator"),
        ({"timestamp_format": " "}, "timestamp_format"),
        ({"timestamp_format": 42}, "timestamp_format"),
        ({"source_timezone": "unknown/timezone"}, "source_timezone"),
        ({"source_timezone": ""}, "source_timezone"),
        ({"source_timezone": 42}, "source_timezone"),
    ],
)
def test_invalid_settings(settings, message):
    with pytest.raises(ValueError, match=message):
        EventLogConfig(**{"input_path": "log.csv", **settings})
