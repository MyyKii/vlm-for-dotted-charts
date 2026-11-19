"""Small saved Phase-1/2 artifacts for offline rendering checks."""

from pathlib import Path

import pandas as pd
import pytest

from data.event_logs import EventLogConfig
from data.event_logs.config import ACTIVITY_COLUMN, CASE_ID_COLUMN, TIMESTAMP_COLUMN
from data.event_logs.preprocessing import EVENT_ID_COLUMN, preprocess_event_log
from data.event_logs.storage import save_processed_event_log
from data.pattern_injection.engine import create_variant, save_variant


@pytest.fixture
def save_source(tmp_path):
    def write(rows: list[tuple[str, str, int]]) -> Path:
        raw = tmp_path / "source.csv"
        source = tmp_path / "source.parquet"
        frame = pd.DataFrame(
            {
                CASE_ID_COLUMN: case,
                ACTIVITY_COLUMN: activity,
                TIMESTAMP_COLUMN: f"2026-01-01T{hour:02d}:00:00Z",
                EVENT_ID_COLUMN: f"{case}-{activity}",
                "org:resource": f"agent-{case}",
            }
            for case, activity, hour in rows
        )
        frame.to_csv(raw, index=False)
        config = EventLogConfig(raw)
        save_processed_event_log(
            preprocess_event_log(frame, config),
            config,
            source,
            dataset_id="fixture",
            split_group_id="fixture-family",
        )
        return source

    return write


@pytest.fixture
def source_path(save_source):
    return save_source(
        [
            ("case-b", "Start", 8),
            ("case-b", "Work", 10),
            ("case-b", "End", 18),
            ("case-a", "Start", 8),
            ("case-a", "Work", 12),
            ("case-a", "Cancel", 12),
            ("case-a", "End", 18),
            ("case-c", "Start", 13),
            ("case-c", "Work", 14),
            ("case-c", "End", 18),
            ("case-d", "Start", 16),
            ("case-d", "End", 19),
        ]
    )


@pytest.fixture
def gap_path(source_path, tmp_path):
    gap = {"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}}
    return save_variant(*create_variant(source_path, [gap]), tmp_path / "injected")


@pytest.fixture
def control_path(source_path, tmp_path):
    return save_variant(*create_variant(source_path, []), tmp_path / "injected")


@pytest.fixture
def batch_path(source_path, tmp_path):
    batch = {
        "preset": "batch_small",
        "parameters": {"num_events": 2, "jitter_seconds": 0},
        "target": {
            "event_ids": ["case-a-Start", "case-c-Start"],
            "center_utc": "2026-01-01T11:00:00Z",
        },
    }
    return save_variant(*create_variant(source_path, [batch]), tmp_path / "injected")
