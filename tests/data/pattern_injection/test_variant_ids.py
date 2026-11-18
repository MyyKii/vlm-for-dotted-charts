"""Recipe length and preset spelling never become filesystem component lengths."""

import json
import re
from tempfile import TemporaryDirectory

import pandas as pd
import pytest

from data.event_logs import EventLogConfig
from data.event_logs.preprocessing import preprocess_event_log
from data.event_logs.storage import save_processed_event_log
from data.pattern_injection.catalog import load_catalog
from data.pattern_injection.engine import create_variant, load_variant, save_variant


@pytest.mark.parametrize(
    "preset,instances",
    [("batch_" + "long" * 100, 1), ("batch_small", 24), ("batch_" + "long" * 100, 16)],
    ids=["long-preset", "repeated-recipe", "long-repeated-recipe"],
)
def test_long_and_repeated_recipes_have_bounded_reproducible_ids(
    tmp_path, monkeypatch, preset, instances
):
    raw = tmp_path / "source.csv"
    rows = [
        {
            "case:concept:name": f"case-{case}",
            "concept:name": activity,
            "identity:id": f"event-{case}-{activity}",
            "time:timestamp": f"2026-01-01T{hour:02}:00:00Z",
        }
        for case in range(2 * instances)
        for activity, hour in [("Start", 8), ("Work", 10 + case % 2), ("End", 18)]
    ]
    pd.DataFrame(rows).to_csv(raw, index=False)
    config = EventLogConfig(raw)
    frame = preprocess_event_log(pd.DataFrame(rows), config)
    source = tmp_path / "source.parquet"
    save_processed_event_log(frame, config, source)
    catalog = load_catalog()
    catalog["presets"][preset] = catalog["presets"]["batch_small"]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog))
    recipe = [
        {
            "preset": preset,
            "parameters": {"num_events": 2, "jitter_seconds": 0},
            "target": {
                "event_ids": [f"event-{2 * index}-Work", f"event-{2 * index + 1}-Work"],
                "center_utc": "2026-01-01T09:00:00Z",
            },
        }
        for index in range(instances)
    ]
    first = create_variant(source, recipe, catalog_path=catalog_path)
    repeated = create_variant(source, recipe, catalog_path=catalog_path)
    variant_id = first[1]["variant_id"]
    assert re.fullmatch(r"batch_[0-9a-f]{16}", variant_id)
    assert len(variant_id) <= 32
    assert variant_id == repeated[1]["variant_id"]
    prefixes = []

    def short_staging_directory(*args, **kwargs):
        prefixes.append(kwargs["prefix"])
        assert len(kwargs["prefix"]) <= 16
        return TemporaryDirectory(*args, **kwargs)

    monkeypatch.setattr("data.pattern_injection.engine.TemporaryDirectory", short_staging_directory)
    output = save_variant(*first, tmp_path / "results")
    assert prefixes
    assert output.name == variant_id
    assert len(load_variant(output)[1]["injections"]) == instances
    changed = json.loads(json.dumps(recipe))
    changed[-1]["seed"] = 99
    assert create_variant(source, changed, catalog_path=catalog_path)[1]["variant_id"] != variant_id


def test_save_rejects_unbounded_external_variant_id(injection_source, tmp_path):
    events, manifest, changes = create_variant(injection_source, [])
    manifest["variant_id"] = "a" * 300
    with pytest.raises(ValueError, match="at most 64"):
        save_variant(events, manifest, changes, tmp_path / "results")
