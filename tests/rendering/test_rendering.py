"""Matched baselines, deterministic Agg drawing, and dense case axes."""

import hashlib
import json

import matplotlib as mpl
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.event_logs import EventLogConfig
from data.event_logs.config import CASE_ID_COLUMN
from data.event_logs.storage import load_processed_event_log, save_processed_event_log
from data.pattern_injection.engine import create_variant, load_variant, save_variant
from rendering.renderer import RenderStyle, render_charts
from rendering.views import load_chart_inputs

STYLE = RenderStyle(width_px=641, height_px=383, dpi=137)


@pytest.mark.parametrize(
    ("selection", "method"),
    [
        ({}, "all_complete_cases"),
        ({"sample_cases": 2, "seed": 7}, "sample_complete_cases"),
        ({"case_ids": ["case-d", "case-a"]}, "explicit_complete_cases"),
    ],
)
def test_recovers_complete_selected_baseline(source_path, tmp_path, selection, method):
    original = load_processed_event_log(source_path)
    variant = save_variant(*create_variant(source_path, [], **selection), tmp_path / "injected")
    inputs = load_chart_inputs(variant)
    resolved = inputs.manifest["source"]["selection"]
    assert resolved["method"] == method
    expected = original.loc[original[CASE_ID_COLUMN].isin(resolved["resolved_case_ids"])]
    assert_frame_equal(inputs.baseline, expected.reset_index(drop=True))
    assert_frame_equal(inputs.modified, inputs.baseline)
    charts = render_charts(inputs, style=STYLE)
    assert charts["baseline"].counts.events == len(expected)
    assert charts["baseline"].canvas.buffer_rgba().tobytes() == (
        charts["modified"].canvas.buffer_rgba().tobytes()
    )


def test_full_method_honors_recorded_ids_and_relative_source(source_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    events, manifest, changes = create_variant(source_path.name, [], case_ids=["case-a"])
    manifest["source"]["selection"]["method"] = "all_complete_cases"
    variant = save_variant(events, manifest, changes, tmp_path / "injected")
    monkeypatch.chdir(tmp_path.parent)
    inputs = load_chart_inputs(variant, source_root=tmp_path)
    assert_frame_equal(inputs.baseline, events)


def test_future_validated_full_selection_can_omit_ids(control_path, monkeypatch):
    events, manifest, changes = load_variant(control_path)
    manifest["source"]["selection"].pop("resolved_case_ids")
    monkeypatch.setattr("rendering.views.load_variant", lambda _: (events, manifest, changes))
    assert_frame_equal(load_chart_inputs(control_path).baseline, events)


def test_baseline_uses_sidecar_next_to_recorded_parquet_path(source_path, tmp_path):
    alias = tmp_path / "linked" / source_path.name
    alias.parent.mkdir()
    alias.symlink_to(source_path)
    source_path.with_suffix(".json").rename(alias.with_suffix(".json"))
    events, manifest, changes = create_variant(alias, [])
    variant = save_variant(events, manifest, changes, tmp_path / "injected")
    assert_frame_equal(load_chart_inputs(variant).baseline, events)


def test_matched_full_view_is_reproducible_and_preserves_inputs(gap_path, source_path):
    paths = [source_path, source_path.with_suffix(".json"), *gap_path.iterdir()]
    before = {path: hashlib.sha256(path.read_bytes()).digest() for path in paths}
    inputs = load_chart_inputs(gap_path)
    charts = render_charts(inputs, style=STYLE)
    repeated = render_charts(inputs, style=STYLE, role="modified")["modified"]
    baseline, modified = charts.values()
    before_axes, after_axes = [chart.canvas.figure.axes[0] for chart in charts.values()]
    assert baseline.view is modified.view
    assert baseline.view.ordered_case_ids == ("case-a", "case-b", "case-c", "case-d")
    assert baseline.view.case_order_source == "baseline"
    assert baseline.view.time_bounds == (
        pd.Timestamp("2026-01-01T08:00:00Z"),
        pd.Timestamp("2026-01-01T21:00:00Z"),
    )
    assert before_axes.get_xlim() == after_axes.get_xlim()
    assert before_axes.get_ylim() == after_axes.get_ylim()
    assert before_axes.get_position().bounds == after_axes.get_position().bounds
    assert baseline.activity_colors == modified.activity_colors
    assert modified.canvas.get_width_height() == (641, 383)
    assert modified.canvas.buffer_rgba().tobytes() == repeated.canvas.buffer_rgba().tobytes()
    assert modified.canvas.buffer_rgba().tobytes() != baseline.canvas.buffer_rgba().tobytes()
    assert {path: hashlib.sha256(path.read_bytes()).digest() for path in paths} == before


@pytest.mark.parametrize("missing_suffix", [".parquet", ".json"])
def test_missing_source_uses_complete_modified_reference(gap_path, source_path, missing_suffix):
    source_path.with_suffix(missing_suffix).unlink()
    inputs = load_chart_inputs(gap_path)
    assert inputs.baseline is None
    chart = render_charts(inputs, role="modified", style=STYLE)["modified"]
    assert chart.view.case_order_source == "modified_fallback"
    assert chart.view.ordered_case_ids == ("case-a", "case-b", "case-c", "case-d")
    assert set(chart.activity_colors) == {"Start", "Work", "End", "Cancel"}
    for role in ("baseline", "both"):
        with pytest.raises(ValueError, match=f"Role '{role}' requires the Phase-1 baseline"):
            render_charts(inputs, role=role, style=STYLE)


def test_present_wrong_source_does_not_become_fallback(gap_path, source_path):
    metadata = source_path.with_suffix(".json")
    metadata.write_text(json.dumps(json.loads(metadata.read_text())))
    with pytest.raises(ValueError, match="Phase-1 JSON checksum differs"):
        load_chart_inputs(gap_path)


def test_baseline_fingerprint_verifies_selected_content(control_path, source_path):
    replacement = load_processed_event_log(source_path)
    replacement["org:resource"] = "different resource"
    metadata = save_processed_event_log(
        replacement, EventLogConfig(source_path.with_suffix(".csv")), source_path, overwrite=True
    )
    manifest_path = control_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source"]["processed_sha256"] = metadata["processed_sha256"]
    manifest["source"]["processed_metadata_sha256"] = hashlib.sha256(
        source_path.with_suffix(".json").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Selected baseline fingerprint differs"):
        load_chart_inputs(control_path)


def test_validated_variant_is_required(gap_path):
    (gap_path / "changes.parquet").unlink()
    with pytest.raises(ValueError, match="Invalid Phase-2 variant.*changes.parquet"):
        load_chart_inputs(gap_path)


def test_dense_view_limits_ticks_without_moving_rows(save_source, tmp_path):
    rows = [(f"case-{index:04d}", "Work", 12 + index % 2) for index in range(450)]
    source = save_source(rows)
    path = save_variant(*create_variant(source, []), tmp_path / "injected")
    inputs = load_chart_inputs(path)
    chart = render_charts(inputs, role="modified", style=STYLE)["modified"]
    fewer = render_charts(
        inputs, role="modified", style=RenderStyle(641, 383, 137, max_case_tick_labels=3)
    )["modified"]
    axes, other_axes = [item.canvas.figure.axes[0] for item in (chart, fewer)]
    assert chart.counts.events == chart.counts.cases == len(rows)
    assert chart.counts.pixels_per_case_row == pytest.approx(0.8 * 383 / len(rows))
    assert "px per row" in chart.diagnostics[0]
    assert len(axes.get_yticklabels()) == 15
    assert tuple(axes.get_yticks()) == chart.case_ticks
    assert fewer.case_ticks == (0, 224, 449)
    assert chart.view.ordered_case_ids == fewer.view.ordered_case_ids
    assert axes.get_ylim() == other_axes.get_ylim() == (-0.5, 449.5)
    assert axes.get_position().bounds == other_axes.get_position().bounds
    assert (axes.collections[0].get_offsets() == other_axes.collections[0].get_offsets()).all()
    assert set(axes.collections[0].get_offsets()[:, 1].tolist()) == set(range(len(rows)))


def test_drawing_uses_fixed_rc_settings_and_restores_caller_settings(control_path):
    inputs = load_chart_inputs(control_path)
    reference = render_charts(inputs, role="modified", style=STYLE)["modified"]
    with mpl.rc_context(
        {"savefig.bbox": "tight", "figure.constrained_layout.use": True, "scatter.marker": "x"}
    ):
        chart = render_charts(inputs, role="modified", style=STYLE)["modified"]
        assert mpl.rcParams["savefig.bbox"] == "tight"
        assert mpl.rcParams["figure.constrained_layout.use"]
    assert chart.geometry.record == reference.geometry.record
    assert chart.png_bytes() == reference.png_bytes()


def test_case_and_activity_labels_are_literal(save_source, tmp_path):
    case_id, activity = r"case-$\literal$", r"work-$\literal$"
    source = save_source([(case_id, activity, 12)])
    variant = save_variant(*create_variant(source, []), tmp_path / "injected")
    style = RenderStyle(800, 400, legend=True)
    chart = render_charts(load_chart_inputs(variant), role="modified", style=style)["modified"]
    assert chart.canvas.figure.axes[0].get_yticklabels()[0].get_text() == case_id
    assert chart.canvas.figure.legends[0].get_texts()[0].get_text() == activity


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"dpi": 0}, "dpi must be a positive integer"),
        ({"width_px": -1}, "width_px must be a positive integer"),
        ({"alpha": 1.5}, "alpha must be between 0 and 1"),
        ({"marker_size": float("nan")}, "marker_size must be a finite number"),
        ({"palette": "unknown"}, "Unknown Matplotlib palette"),
        ({"background": "unknown"}, "Invalid chart background"),
        ({"max_case_tick_labels": -1}, "max_case_tick_labels must be a nonnegative integer"),
    ],
)
def test_invalid_chart_style(settings, message):
    with pytest.raises(ValueError, match=message):
        RenderStyle(**settings)
