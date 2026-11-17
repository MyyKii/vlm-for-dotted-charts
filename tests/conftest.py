"""Small, offline event-log sources shared by unit and integration tests."""

import gzip
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_csv() -> Path:
    return Path(__file__).parent / "fixtures" / "event_logs" / "sample.csv"


@pytest.fixture
def sample_xes() -> Path:
    return Path(__file__).parent / "fixtures" / "event_logs" / "sample.xes"


@pytest.fixture
def gzipped_xes(sample_xes) -> bytes:
    return gzip.compress(sample_xes.read_bytes(), mtime=0)


@pytest.fixture
def download_response(monkeypatch):
    """Mock the HTTP boundary while exercising real download/file handling."""
    from requests import Response
    from requests.structures import CaseInsensitiveDict

    response = MagicMock(spec=Response)
    response.status_code = 200
    response.headers = CaseInsensitiveDict()
    response.__enter__.return_value = response
    response.iter_content.return_value = iter([b"event log"])
    monkeypatch.setattr("data.event_logs.downloader.requests.get", MagicMock(return_value=response))
    return response
