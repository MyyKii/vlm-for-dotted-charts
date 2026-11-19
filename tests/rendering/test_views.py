"""Half-open windows, candidate focus, and shared case/activity selection."""

from io import BytesIO

import pandas as pd
import pytest
from PIL import Image

from data.event_logs.preprocessing import EVENT_ID_COLUMN
from data.pattern_injection.engine import create_variant, save_variant
from rendering.renderer import RenderStyle, render_charts
from rendering.views import ViewSpec, load_chart_inputs, select_view


def window(start_hour, end_hour, **filters):
    return ViewSpec(
        mode="time_window",
        start_utc=f"2026-01-01T{start_hour:02d}:00:00Z",
        end_utc=f"2026-01-01T{end_hour:02d}:00:00Z",
        **filters,
    )


def test_partial_time_window_aligns_union_of_moved_cases(gap_path):
    inputs = load_chart_inputs(gap_path)
    spec = window(14, 15)
    view = select_view(inputs, spec)
    assert view.ordered_case_ids == ("case-a", "case-c")
    assert view.events("baseline")[EVENT_ID_COLUMN].tolist() == ["case-c-Work"]
    assert view.events("modified")[EVENT_ID_COLUMN].tolist() == ["case-a-Work", "case-a-Cancel"]
    assert view.events("modified").columns.equals(inputs.modified.columns)
    assert view.time_bounds == (spec.start_utc, spec.end_utc)


def test_combined_filters_preserve_case_order_and_complete_palette(gap_path):
    inputs = load_chart_inputs(gap_path)
    style = RenderStyle(641, 383, legend=True)
    full = render_charts(inputs, role="modified", style=style)["modified"]
    spec = window(14, 15, case_ids=["case-d", "case-a"], activities=["Cancel"])
    charts = render_charts(inputs, view=spec, style=style)
    baseline, modified = charts.values()
    assert baseline.counts.events == 0
    assert "No baseline events" in baseline.diagnostics[0]
    assert modified.counts.events == 1
    for chart in charts.values():
        assert chart.view.ordered_case_ids == ("case-a", "case-d")
        assert chart.counts.cases == 2
        assert chart.activity_colors == full.activity_colors
        assert chart.canvas.figure.axes[0].get_ylim() == (-0.5, 1.5)
        assert len(chart.canvas.figure.axes[0].get_xticklabels()) <= 6
        assert len(chart.canvas.figure.legends[0].get_texts()) == 1
        assert chart.canvas.figure.legends[0].get_texts()[0].get_text() == "Cancel"


def test_empty_gap_focus_keeps_shared_view_and_optional_overlay(gap_path):
    inputs = load_chart_inputs(gap_path)
    spec = ViewSpec(mode="focused", region_id="region_001", context="15min")
    style = RenderStyle(641, 383)
    view = select_view(inputs, spec)
    assert view.focus == ("inj_001", "region_001")
    assert view.time_bounds == (
        pd.Timestamp("2026-01-01T11:45:00Z"),
        pd.Timestamp("2026-01-01T14:15:00Z"),
    )
    assert view.ordered_case_ids == ("case-a", "case-c")
    assert "case-c-Start" in view.events("baseline")[EVENT_ID_COLUMN].tolist()
    assert not view.events("modified")[EVENT_ID_COLUMN].str.startswith("case-c").any()

    empty = render_charts(inputs, view=window(12, 14), style=style)
    assert empty["modified"].counts.events == 0
    assert empty["baseline"].counts.events == 3
    assert empty["modified"].view.ordered_case_ids == ("case-a", "case-c")
    before, after = [item.canvas.figure.axes[0] for item in empty.values()]
    assert before.get_xlim() == after.get_xlim()
    assert before.get_ylim() == after.get_ylim()
    assert before.get_window_extent().bounds == after.get_window_extent().bounds

    clean = render_charts(inputs, view=spec, style=style)
    annotated = render_charts(inputs, view=spec, style=style, show_candidate_regions=True)
    assert clean["baseline"].png_bytes() == annotated["baseline"].png_bytes()
    assert clean["modified"].png_bytes() != annotated["modified"].png_bytes()
    with Image.open(BytesIO(annotated["modified"].png_bytes())) as image:
        assert image.size == (641, 383)
    axes = annotated["modified"].canvas.figure.axes[0]
    assert len(axes.patches) == 1
    assert axes.get_xlim() == clean["modified"].canvas.figure.axes[0].get_xlim()


def test_batch_focus_on_instant_and_missing_baseline_order(batch_path, source_path):
    inputs = load_chart_inputs(batch_path)
    spec = ViewSpec(mode="focused", injection_id="inj_001", context="30min")
    view = select_view(inputs, spec)
    assert view.time_bounds == (
        pd.Timestamp("2026-01-01T10:30:00Z"),
        pd.Timestamp("2026-01-01T11:30:00Z"),
    )
    assert view.events("baseline").empty
    assert view.events("modified")[EVENT_ID_COLUMN].tolist() == ["case-a-Start", "case-c-Start"]
    assert select_view(inputs).ordered_case_ids == ("case-a", "case-b", "case-c", "case-d")
    source_path.unlink()
    fallback = select_view(load_chart_inputs(batch_path), ViewSpec(activities=["Start"]))
    assert fallback.case_order_source == "modified_fallback"
    assert fallback.ordered_case_ids == ("case-b", "case-a", "case-c", "case-d")


def test_views_with_no_events_report_empty_and_keep_requested_case_rows(control_path):
    inputs = load_chart_inputs(control_path)
    spec = window(1, 2)
    charts = render_charts(inputs, view=spec, style=RenderStyle(641, 383))
    for role, chart in charts.items():
        assert chart.counts.events == chart.counts.cases == 0
        assert chart.counts.pixels_per_case_row is None
        assert f"No {role} events match this view." in chart.diagnostics
    selected = select_view(inputs, window(1, 2, case_ids=["case-c", "case-b"]))
    assert selected.ordered_case_ids == ("case-b", "case-c")


def test_subsecond_view_preserves_exact_half_open_bounds(control_path):
    start = "2026-01-01T12:00:00Z"
    end = "2026-01-01T12:00:00.000000001Z"
    spec = ViewSpec(mode="time_window", start_utc=start, end_utc=end)
    chart = render_charts(
        load_chart_inputs(control_path), view=spec, role="modified", style=RenderStyle(641, 383)
    )["modified"]
    assert chart.view.time_bounds == (pd.Timestamp(start), pd.Timestamp(end))
    assert chart.view.modified[EVENT_ID_COLUMN].tolist() == ["case-a-Work", "case-a-Cancel"]
    axes = chart.canvas.figure.axes[0]
    assert axes.get_xlim() == (0, pytest.approx(1 / 86_400_000_000_000))
    assert axes.collections[0].get_offsets()[:, 0].tolist() == [0, 0]


@pytest.mark.parametrize(
    ("options", "error"),
    [
        ({"mode": "unknown"}, "Unknown view mode"),
        ({"start_utc": "2026-01-01"}, "require time_window"),
        ({"context": "1h"}, "require focused"),
        ({"mode": "time_window"}, "start_utc"),
        ({"mode": "time_window", "start_utc": "2026-01-01T12:00"}, "Invalid start_utc"),
        (
            {"mode": "time_window", "start_utc": "2026-01-02Z", "end_utc": "2026-01-01Z"},
            "Invalid start_utc",
        ),
        (
            {
                "mode": "time_window",
                "start_utc": "2026-01-02T00:00Z",
                "end_utc": "2026-01-01T00:00Z",
            },
            "end_utc > start_utc",
        ),
        ({"mode": "focused", "context": "1h"}, "injection_id or region_id"),
        ({"mode": "focused", "injection_id": "inj_001"}, "positive context"),
        ({"mode": "focused", "injection_id": "inj_001", "context": "0min"}, "must be positive"),
        ({"activities": "Cancel"}, "activities must be a nonempty"),
        ({"case_ids": []}, "case_ids must be a nonempty"),
    ],
)
def test_invalid_view_configuration(options, error):
    with pytest.raises(ValueError, match=error):
        ViewSpec(**options)


def test_unknown_filters_and_region_ids(gap_path):
    inputs = load_chart_inputs(gap_path)
    for spec, error in (
        (ViewSpec(case_ids=["missing-case"]), "Unknown case IDs.*missing-case"),
        (ViewSpec(activities=["missing-activity"]), "Unknown activities.*missing-activity"),
        (ViewSpec(mode="focused", injection_id="inj_999", context="1h"), "inj_999"),
        (ViewSpec(mode="focused", region_id="region_999", context="1h"), "region_999"),
    ):
        with pytest.raises(ValueError, match=error):
            select_view(inputs, spec)


def test_requires_unambiguous_region_reference(source_path, tmp_path):
    recipe = [
        {"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}},
        {
            "preset": "batch_small",
            "parameters": {"num_events": 2, "jitter_seconds": 0},
            "target": {
                "event_ids": ["case-a-Start", "case-b-Work"],
                "center_utc": "2026-01-01T09:00:00Z",
            },
        },
    ]
    path = save_variant(*create_variant(source_path, recipe), tmp_path / "injected")
    inputs = load_chart_inputs(path)
    with pytest.raises(ValueError, match="Ambiguous target region.*region_001"):
        select_view(inputs, ViewSpec(mode="focused", region_id="region_001", context="1h"))
    spec = ViewSpec(mode="focused", injection_id="inj_002", region_id="region_001", context="1h")
    assert select_view(inputs, spec).focus == ("inj_002", "region_001")
