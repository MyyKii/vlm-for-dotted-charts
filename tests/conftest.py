"""Small, offline event-log sources shared by unit and integration tests."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_csv() -> Path:
    return Path(__file__).parent / "fixtures" / "event_logs" / "sample.csv"


@pytest.fixture
def sample_xes() -> Path:
    return Path(__file__).parent / "fixtures" / "event_logs" / "sample.xes"
