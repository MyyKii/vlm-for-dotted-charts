"""Deterministic preparation with explicit timestamps and stable identities."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.event_logs import EventLogConfig
from data.event_logs.loader import load_event_log
from data.event_logs.preprocessing import preprocess_event_log


def test_column_mapping_order_and_input_immutability():
    original = pd.DataFrame(
        {
            "case": ["b", "a", "a", "a"],
            "activity": ["Finish", "Later", "First", "Tie"],
            "timestamp": [
                "2026-01-02T12:00:00Z",
                "2026-01-01T12:00:00Z",
                "2026-01-01T10:00:00Z",
                "2026-01-01T10:00:00Z",
            ],
            "org:resource": ["r0", "r1", "r2", "r3"],
            "cost": [4, 3, 2, 1],
        },
        index=[8, 5, 5, 9],
    )
    before = original.copy(deep=True)
    config = EventLogConfig(
        "log.csv", case_id_column="case", activity_column="activity", timestamp_column="timestamp"
    )

    processed = preprocess_event_log(original, config)

    assert processed["case:concept:name"].tolist() == ["a", "a", "a", "b"]
    assert processed["concept:name"].tolist() == ["First", "Tie", "Later", "Finish"]
    assert processed["@@source_row"].tolist() == [2, 3, 1, 0]
    assert processed["identity:id"].tolist() == [
        "source-row:2",
        "source-row:3",
        "source-row:1",
        "source-row:0",
    ]
    assert processed["org:resource"].tolist() == ["r2", "r3", "r1", "r0"]
    assert processed["cost"].tolist() == [2, 1, 3, 4]
    assert str(processed["time:timestamp"].dt.tz) == "UTC"
    assert_frame_equal(original, before)
    assert_frame_equal(processed, preprocess_event_log(original, config))
    assert_frame_equal(processed, preprocess_event_log(processed, config))


@pytest.mark.parametrize("source_format", ["csv", "xes"])
def test_loading_then_preprocessing(sample_csv, sample_xes, source_format):
    config = (
        EventLogConfig(
            sample_csv,
            case_id_column="case",
            activity_column="activity",
            timestamp_column="timestamp",
        )
        if source_format == "csv"
        else EventLogConfig(sample_xes)
    )
    processed = preprocess_event_log(load_event_log(config), config)

    assert processed["identity:id"].tolist() == ["e-0", "e-1", "e-2", "e-3"]
    assert processed["time:timestamp"].iloc[-1] == pd.Timestamp("2026-01-02T09:30:00Z")


def timestamp_frame(values):
    return pd.DataFrame(
        {
            "case:concept:name": ["a"] * len(values),
            "concept:name": ["Start"] * len(values),
            "time:timestamp": values,
        }
    )


@pytest.mark.parametrize(
    ("values", "timezone", "expected"),
    [
        (
            ["2026-01-01T12:00:00+02:00", "2026-01-01T12:00:00-03:00"],
            None,
            ["2026-01-01T10:00:00Z", "2026-01-01T15:00:00Z"],
        ),
        (
            ["2026-01-01T12:00:00", "2026-07-01T12:00:00"],
            "Europe/Berlin",
            ["2026-01-01T11:00:00Z", "2026-07-01T10:00:00Z"],
        ),
        (
            ["2026-01-01T12:00:00", "2026-01-01T12:00:00Z"],
            "Europe/Berlin",
            ["2026-01-01T11:00:00Z", "2026-01-01T12:00:00Z"],
        ),
        (pd.to_datetime(["2026-01-01T12:00:00Z"]), None, ["2026-01-01T12:00:00Z"]),
        (pd.to_datetime(["2026-01-01T12:00:00"]), "UTC", ["2026-01-01T12:00:00Z"]),
        (["2026-01-01T12:00:00.123456789Z"], None, ["2026-01-01T12:00:00.123456789Z"]),
    ],
)
def test_timestamp_conversion(values, timezone, expected):
    processed = preprocess_event_log(
        timestamp_frame(values), EventLogConfig("log.csv", source_timezone=timezone)
    )

    assert processed["time:timestamp"].tolist() == pd.to_datetime(expected, utc=True).tolist()


def test_explicit_timestamp_format():
    processed = preprocess_event_log(
        timestamp_frame(["02.01.2026 12:30"]),
        EventLogConfig("log.csv", timestamp_format="%d.%m.%Y %H:%M", source_timezone="UTC"),
    )
    assert processed["time:timestamp"].iloc[0] == pd.Timestamp("2026-01-02T12:30:00Z")


@pytest.mark.parametrize(
    ("value", "timezone", "message"),
    [
        ("not-a-date", None, "time:timestamp.*row 0"),
        (None, None, "time:timestamp.*row 0"),
        ("", None, "time:timestamp.*row 0"),
        (123, None, "numeric timestamps"),
        ("2026-01-01T12:00:00", None, "requires source_timezone"),
        ("01/02/2026 12:00", "UTC", "time:timestamp"),
        ("2026-10-25T02:30:00", "Europe/Berlin", "time:timestamp.*row 0"),
        ("2026-03-29T02:30:00", "Europe/Berlin", "time:timestamp.*row 0"),
    ],
)
def test_invalid_or_ambiguous_timestamps(value, timezone, message):
    with pytest.raises(ValueError, match=message):
        preprocess_event_log(
            timestamp_frame([value]), EventLogConfig("log.csv", source_timezone=timezone)
        )


def test_mixed_awareness_requires_timezone():
    with pytest.raises(ValueError, match="row 1.*requires source_timezone"):
        preprocess_event_log(
            timestamp_frame(["2026-01-01T12:00:00Z", "2026-01-01T12:00:00"]),
            EventLogConfig("log.csv"),
        )


def test_duplicate_columns_rejected():
    frame = pd.DataFrame([["a", "a"]], columns=["concept:name", "concept:name"])
    with pytest.raises(ValueError, match="column names must be unique"):
        preprocess_event_log(frame, EventLogConfig("log.csv"))


def test_invalid_source_positions():
    frame = timestamp_frame(["2026-01-01T12:00:00Z"] * 2)
    frame["@@source_row"] = [1, 1]
    with pytest.raises(ValueError, match="@@source_row"):
        preprocess_event_log(frame, EventLogConfig("log.csv"))
