"""Parquet round trips preserve typed values and reproducible provenance."""

import hashlib
import json
import os

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.event_logs import EventLogConfig
from data.event_logs.loader import load_event_log
from data.event_logs.preprocessing import preprocess_event_log
from data.event_logs.storage import load_processed_event_log, save_processed_event_log


@pytest.fixture
def prepared_log(sample_csv):
    config = EventLogConfig(
        sample_csv, case_id_column="case", activity_column="activity", timestamp_column="timestamp"
    )
    return preprocess_event_log(load_event_log(config), config), config


def test_save_and_reload(prepared_log, tmp_path):
    frame, config = prepared_log
    original = config.input_path.read_bytes()
    output = tmp_path / "processed" / "receipt.parquet"

    metadata = save_processed_event_log(frame, config, output)
    reloaded = load_processed_event_log(output)

    assert output.is_file()
    assert output.with_suffix(".json").is_file()
    assert json.loads(output.with_suffix(".json").read_text()) == metadata
    assert_frame_equal(frame, reloaded, check_exact=True)
    assert metadata["num_events"] == 4
    assert metadata["num_cases"] == 2
    assert metadata["num_activities"] == 3
    assert metadata["source_file"] == config.input_path.name
    assert metadata["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert metadata["source_id"] == f"sha256:{hashlib.sha256(original).hexdigest()}"
    assert metadata["dataset_id"] == "sample"
    assert metadata["split_group_id"] == "sample"
    assert metadata["time_range"] == {
        "start": "2026-01-01T09:00:00+00:00",
        "end": "2026-01-02T09:30:00+00:00",
    }
    assert metadata["storage_format"] == "parquet"
    assert metadata["storage_version"] == 1
    assert metadata["schema"]
    assert metadata["pm4py_version"]
    assert metadata["processing_config"]["timestamp_format"] == "ISO8601"
    assert config.input_path.read_bytes() == original


def test_deterministic_data_and_metadata(prepared_log, tmp_path):
    frame, config = prepared_log
    first = tmp_path / "first" / "log.parquet"
    second = tmp_path / "second" / "log.parquet"

    first_metadata = save_processed_event_log(frame, config, first)
    second_metadata = save_processed_event_log(frame, config, second)

    assert first_metadata == second_metadata
    assert first.read_bytes() == second.read_bytes()
    assert first.with_suffix(".json").read_bytes() == second.with_suffix(".json").read_bytes()
    assert_frame_equal(load_processed_event_log(first), load_processed_event_log(second))


def test_group_identifiers(prepared_log, tmp_path):
    frame, config = prepared_log
    metadata = save_processed_event_log(
        frame,
        config,
        tmp_path / "log.parquet",
        dataset_id="receipt-january",
        split_group_id="receipt",
    )
    assert metadata["dataset_id"] == "receipt-january"
    assert metadata["split_group_id"] == "receipt"


def test_typed_optional_attributes_and_nanoseconds(prepared_log, tmp_path):
    frame, config = prepared_log
    frame["time:timestamp"] += pd.Timedelta(123456789, unit="ns")
    frame["nullable_int"] = pd.Series([1, None, 3, 4], dtype="Int64")
    frame["nullable_bool"] = pd.Series([True, None, False, True], dtype="boolean")
    frame["literal_text"] = pd.Series(["001", "NA", "", None], dtype="string")
    frame["category"] = pd.Categorical(["b", "a", "a", "b"])
    output = tmp_path / "log.parquet"

    save_processed_event_log(frame, config, output)

    assert_frame_equal(frame, load_processed_event_log(output), check_exact=True)


@pytest.mark.parametrize("existing_suffix", [".parquet", ".json"])
def test_no_accidental_overwrite(prepared_log, tmp_path, existing_suffix):
    frame, config = prepared_log
    output = tmp_path / "log.parquet"
    existing = output.with_suffix(existing_suffix)
    existing.write_bytes(b"keep me")

    with pytest.raises(FileExistsError, match="already exists"):
        save_processed_event_log(frame, config, output)

    assert existing.read_bytes() == b"keep me"
    assert len(list(tmp_path.iterdir())) == 1


def test_explicit_overwrite(prepared_log, tmp_path):
    frame, config = prepared_log
    output = tmp_path / "log.parquet"
    save_processed_event_log(frame, config, output)
    changed = frame.copy()
    changed.loc[0, "org:resource"] = "updated"

    save_processed_event_log(changed, config, output, overwrite=True)

    assert_frame_equal(changed, load_processed_event_log(output))


@pytest.mark.parametrize(
    "key", ["storage_version", "schema", "num_events", "num_cases", "time_range"]
)
def test_metadata_mismatch_is_rejected(prepared_log, tmp_path, key):
    frame, config = prepared_log
    output = tmp_path / "log.parquet"
    metadata = save_processed_event_log(frame, config, output)
    metadata[key] = -1
    output.with_suffix(".json").write_text(json.dumps(metadata))

    with pytest.raises(ValueError, match="storage_version|schema|Event count|num_cases|time_range"):
        load_processed_event_log(output)


def test_data_checksum_mismatch_is_rejected(prepared_log, tmp_path):
    frame, config = prepared_log
    output = tmp_path / "log.parquet"
    save_processed_event_log(frame, config, output)
    frame.iloc[:1].to_parquet(output, engine="pyarrow", index=False)

    with pytest.raises(ValueError, match="checksum"):
        load_processed_event_log(output)


def test_unsupported_attribute_fails_without_outputs(prepared_log, tmp_path):
    frame, config = prepared_log
    frame["unsupported"] = [object()] * len(frame)
    output = tmp_path / "log.parquet"

    with pytest.raises(ValueError, match="Parquet cannot preserve"):
        save_processed_event_log(frame, config, output)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("column", ["identity:id", "@@source_row"])
def test_unprepared_log_is_rejected(prepared_log, tmp_path, column):
    frame, config = prepared_log
    with pytest.raises(ValueError, match=column):
        save_processed_event_log(frame.drop(columns=column), config, tmp_path / "log.parquet")
    assert list(tmp_path.iterdir()) == []


def test_unsupported_output_format(prepared_log, tmp_path):
    frame, config = prepared_log
    with pytest.raises(ValueError, match=".parquet extension"):
        save_processed_event_log(frame, config, tmp_path / "log.csv")


@pytest.mark.parametrize("field", ["dataset_id", "split_group_id"])
def test_empty_identifiers(prepared_log, tmp_path, field):
    frame, config = prepared_log
    with pytest.raises(ValueError, match=field):
        save_processed_event_log(frame, config, tmp_path / "log.parquet", **{field: " "})


def test_source_alias_is_not_overwritten(prepared_log, tmp_path):
    frame, config = prepared_log
    output = tmp_path / "log.parquet"
    output.symlink_to(config.input_path)
    original = config.input_path.read_bytes()

    with pytest.raises(ValueError, match="must not overwrite the source"):
        save_processed_event_log(frame, config, output, overwrite=True)

    assert config.input_path.read_bytes() == original


def test_metadata_publication_failure_rolls_back_output(prepared_log, tmp_path, monkeypatch):
    frame, config = prepared_log
    output = tmp_path / "log.parquet"
    original_link = os.link

    def fail_metadata_link(source, destination):
        if destination.suffix == ".json":
            raise OSError("metadata publication failed")
        original_link(source, destination)

    monkeypatch.setattr(os, "link", fail_metadata_link)
    with pytest.raises(OSError, match="metadata publication failed"):
        save_processed_event_log(frame, config, output)

    assert list(tmp_path.iterdir()) == []
