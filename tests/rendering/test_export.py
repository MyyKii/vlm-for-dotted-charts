"""PNG geometry, saved provenance, chart identity, and exclusive publication."""

import hashlib
import json
import math
import os

import pandas as pd
import pytest
from matplotlib import dates
from PIL import Image, ImageColor

from data.event_logs.config import CASE_ID_COLUMN, TIMESTAMP_COLUMN
from data.event_logs.preprocessing import EVENT_ID_COLUMN
from data.pattern_injection.engine import create_variant, save_variant
from rendering.export import export_charts
from rendering.geometry import PixelGeometry, data_to_pixel
from rendering.renderer import RenderStyle, render_charts
from rendering.views import ViewSpec, is_event_rendered, load_chart_inputs, select_view

STYLE = RenderStyle(width_px=701, height_px=419, dpi=137)


def read_record(directory):
    return json.loads((directory / "rendering.json").read_text(encoding="utf-8"))


def assert_marker_near(image, position, color):
    x, y = position
    rgba = (*ImageColor.getrgb(color), 255)
    samples = [
        (column + 0.5, row + 0.5)
        for column in range(math.floor(x) - 3, math.floor(x) + 4)
        for row in range(math.floor(y) - 3, math.floor(y) + 4)
        if image.getpixel((column, row)) == rgba
    ]
    assert any(math.dist(position, pixel) <= 3 for pixel in samples)


@pytest.fixture
def geometry_inputs(save_source, tmp_path):
    source = save_source(
        [
            ("case-a", "Start", 8),
            ("case-a", "End", 18),
            ("case-b", "Start", 9),
            ("case-b", "Work", 13),
            ("case-c", "Start", 10),
            ("case-c", "End", 18),
        ]
    )
    return load_chart_inputs(save_variant(*create_variant(source, []), tmp_path / "injected"))


@pytest.mark.parametrize("width,height,dpi", [(927, 413, 173), (1001, 517, 200)])
def test_mapping_matches_decoded_png_at_limits_and_row_centers(
    geometry_inputs, tmp_path, width, height, dpi
):
    # Antialiasing and the plot spine can obscure a center exactly on an edge.
    # Check for an opaque marker pixel no more than 3 px from the geometric center.
    style = RenderStyle(width, height, dpi, marker_size=30, alpha=1, palette="tab10")
    output = export_charts(geometry_inputs, role="modified", style=style, output_root=tmp_path)
    path = output["modified"]
    record = read_record(path)
    geometry = PixelGeometry.from_metadata(record)
    assert geometry.record["origin"] == "top_left"
    assert geometry.record["pixel_reference"] == "edges"
    assert set(entry.name for entry in path.iterdir()) == {"chart.png", "rendering.json"}
    assert [geometry.record["width_px"], geometry.record["height_px"]] == [width, height]
    left, top, right, bottom = width * 0.13, height * 0.05, width * 0.78, height * 0.85
    assert geometry.record["plot_rect_px"] == pytest.approx([left, top, right, bottom], abs=1e-7)
    assert geometry.ordered_case_ids == ("case-a", "case-b", "case-c")
    assert geometry.record["ylim_index"] == [-0.5, 2.5]

    row_height = (bottom - top) / 3
    locations = [
        (8, "case-a", "Start", (left, bottom - row_height / 2)),
        (13, "case-b", "Work", ((left + right) / 2, (top + bottom) / 2)),
        (18, "case-c", "End", (right, top + row_height / 2)),
    ]
    with Image.open(path / "chart.png") as image:
        assert image.size == (width, height)
        assert image.info["dpi"] == pytest.approx((dpi, dpi), abs=0.02)
        for hour, case, activity, expected in locations:
            actual = data_to_pixel(f"2026-01-01T{hour:02d}:00:00Z", case, geometry)
            assert actual == pytest.approx(expected, abs=1e-6)
            assert_marker_near(image, actual, record["style"]["activity_colors"][activity])

    assert data_to_pixel("2026-01-01T07:00:00Z", "case-a", geometry)[0] < left
    assert data_to_pixel("2026-01-01T19:00:00Z", "case-a", geometry)[0] > right
    with pytest.raises(ValueError, match="case-unknown.*no displayed row"):
        data_to_pixel("2026-01-01T08:00:00Z", "case-unknown", geometry)


def test_filtered_membership_is_separate_from_coordinates(gap_path, tmp_path):
    inputs = load_chart_inputs(gap_path)
    spec = ViewSpec(
        mode="time_window",
        start_utc="2026-01-01T14:00:00Z",
        end_utc="2026-01-01T15:00:00Z",
        activities=["Work"],
    )
    style = RenderStyle(701, 419, 137, marker_size=30, alpha=1)
    output = export_charts(inputs, view=spec, style=style, output_root=tmp_path)
    record = read_record(output["modified"])
    geometry = PixelGeometry.from_metadata(record)
    stored = record["view"]
    replayed = select_view(
        inputs,
        ViewSpec(
            mode=stored["mode"],
            start_utc=stored["requested_time_window_utc"][0],
            end_utc=stored["requested_time_window_utc"][1],
            case_ids=stored["case_filter"],
            activities=stored["activity_filter"],
        ),
    )

    event = inputs.modified.set_index(EVENT_ID_COLUMN).loc["case-a-Work"]
    colocated = inputs.modified.set_index(EVENT_ID_COLUMN).loc["case-a-Cancel"]
    assert tuple(event[[CASE_ID_COLUMN, TIMESTAMP_COLUMN]]) == tuple(
        colocated[[CASE_ID_COLUMN, TIMESTAMP_COLUMN]]
    )
    assert is_event_rendered("case-a-Work", replayed, role="modified")
    assert not is_event_rendered("case-a-Cancel", replayed, role="modified")
    assert not is_event_rendered("case-a-Work", replayed, role="baseline")
    assert is_event_rendered("case-c-Work", replayed, role="baseline")
    assert not is_event_rendered("case-c-Work", replayed, role="modified")
    assert not is_event_rendered("missing-event", replayed, role="modified")
    position = data_to_pixel(event[TIMESTAMP_COLUMN], event[CASE_ID_COLUMN], geometry)
    assert position == data_to_pixel(
        colocated[TIMESTAMP_COLUMN], colocated[CASE_ID_COLUMN], geometry
    )

    chart = render_charts(inputs, view=spec, role="modified", style=style)["modified"]
    axes = chart.canvas.figure.axes[0]
    x, y = axes.transData.transform((dates.date2num(event[TIMESTAMP_COLUMN].to_datetime64()), 0))
    assert position == pytest.approx((x, style.height_px - y), abs=1e-7)
    with Image.open(output["modified"] / "chart.png") as image:
        assert_marker_near(image, position, record["style"]["activity_colors"]["Work"])
    assert record["counts"]["events"] == 1
    assert record["counts"]["filtering"] == {"time": True, "cases": False, "activities": True}
    assert record["view"]["ordered_case_ids"] == ["case-a", "case-c"]


def test_subsecond_geometry_can_be_restored(control_path, tmp_path):
    start = "2026-01-01T12:00:00.000000000Z"
    end = "2026-01-01T12:00:00.000000010Z"
    inputs = load_chart_inputs(control_path)
    outputs = export_charts(
        inputs,
        view=ViewSpec(mode="time_window", start_utc=start, end_utc=end),
        role="modified",
        style=STYLE,
        output_root=tmp_path,
    )
    geometry = PixelGeometry.from_metadata(read_record(outputs["modified"]))
    left, top, right, bottom = geometry.record["plot_rect_px"]
    assert pd.Timestamp(geometry.record["time_origin_utc"]) == pd.Timestamp(start)
    assert data_to_pixel(start, "case-a", geometry) == pytest.approx((left, (top + bottom) / 2))
    assert data_to_pixel(end, "case-a", geometry) == pytest.approx((right, (top + bottom) / 2))


def test_full_view_with_one_timestamp_has_a_nonsingular_axis(save_source, tmp_path):
    source = save_source([("case-a", "Work", 12)])
    variant = save_variant(*create_variant(source, []), tmp_path / "injected")
    chart = render_charts(load_chart_inputs(variant), role="modified", style=STYLE)["modified"]
    assert chart.counts.events == chart.counts.cases == 1
    left, top, right, bottom = chart.geometry.record["plot_rect_px"]
    pixel = data_to_pixel("2026-01-01T12:00:00Z", "case-a", chart.geometry)
    assert pixel == pytest.approx(((left + right) / 2, (top + bottom) / 2), abs=1e-6)


def test_saved_date_epoch_is_used_when_reloading_geometry(geometry_inputs, monkeypatch):
    chart = render_charts(geometry_inputs, role="modified", style=STYLE)["modified"]
    time = "2026-01-01T13:00:00.01234Z"
    expected = data_to_pixel(time, "case-b", chart.geometry)
    monkeypatch.setattr(dates, "get_epoch", lambda: "2000-01-01T00:00:00")
    assert data_to_pixel(time, "case-b", chart.geometry) == pytest.approx(expected, abs=1e-7)


def test_stable_pair_provenance_and_clean_export(gap_path, tmp_path):
    inputs = load_chart_inputs(gap_path)
    spec = ViewSpec(mode="focused", injection_id="inj_001", context="1h")
    clean = render_charts(inputs, view=spec, style=STYLE)
    overlaid = render_charts(inputs, view=spec, style=STYLE, show_candidate_regions=True)
    first = export_charts(inputs, view=spec, style=STYLE, output_root=tmp_path / "first")
    second = export_charts(inputs, view=spec, style=STYLE, output_root=tmp_path / "second")
    baseline, modified = (read_record(path) for path in first.values())
    assert baseline["view_id"] == modified["view_id"]
    assert baseline["chart_id"] != modified["chart_id"]
    assert baseline["geometry"] == modified["geometry"]
    assert baseline["view"] == modified["view"]
    assert baseline["style"] == modified["style"]
    assert modified["view"]["region_id"] == "region_001"
    assert modified["view"]["context_ns"] == 3_600_000_000_000
    assert (
        modified["injections"][0]["target_regions"]
        == (inputs.manifest["injections"][0]["target_regions"])
    )
    assert (
        modified["source_variant"]["events_sha256"]
        == (inputs.manifest["files"]["events.parquet"]["sha256"])
    )
    assert (
        modified["source_variant"]["selected_baseline_sha256"]
        == (inputs.manifest["source"]["selected_baseline_sha256"])
    )
    assert modified["source_variant"]["directory"] == str(gap_path)
    assert modified["style"]["backend"] == "Agg"
    assert set(modified["style"]["software_versions"]) >= {"matplotlib", "pillow", "pandas"}
    assert modified["style"]["activity_color_source"] == "baseline"
    assert modified["style"]["case_ticks"] == [
        {"row": row, "case_id": case}
        for row, case in enumerate(modified["view"]["ordered_case_ids"])
    ]
    assert modified["schema_version"] == 1
    assert modified["dataset_id"] == "fixture"
    assert modified["split_group_id"] == "fixture-family"
    for role, output in first.items():
        image_bytes = (output / "chart.png").read_bytes()
        assert image_bytes == clean[role].png_bytes()
        assert image_bytes == (second[role] / "chart.png").read_bytes()
        assert read_record(output) == read_record(second[role])
        assert read_record(output)["image_sha256"] == hashlib.sha256(image_bytes).hexdigest()
        assert output.name == read_record(output)["chart_id"]
    assert (first["modified"] / "chart.png").read_bytes() != overlaid["modified"].png_bytes()


def test_different_filters_dimensions_and_fallback_have_different_ids(
    gap_path, source_path, tmp_path
):
    inputs = load_chart_inputs(gap_path)
    root = tmp_path / "exports"
    paired = export_charts(inputs, style=STYLE, output_root=root)
    filtered = export_charts(
        inputs, view=ViewSpec(activities=["Work"]), style=STYLE, output_root=root
    )
    resized = export_charts(inputs, style=RenderStyle(801, 419, 137), output_root=root)
    source_path.unlink()
    standalone = export_charts(
        load_chart_inputs(gap_path), role="modified", style=STYLE, output_root=root
    )
    records = [
        read_record(outputs["modified"]) for outputs in (paired, filtered, resized, standalone)
    ]
    assert len({record["view_id"] for record in records}) == len(records)
    assert records[-1]["view"]["case_order_source"] == "modified_fallback"
    assert records[-1]["style"]["activity_color_source"] == "modified_fallback"


def test_export_refuses_existing_chart_before_creating_its_partner(control_path, tmp_path):
    inputs = load_chart_inputs(control_path)
    root = tmp_path / "charts"
    charts = export_charts(inputs, role="modified", style=STYLE, output_root=root)
    modified = charts["modified"]
    before = {path.name: path.read_bytes() for path in modified.iterdir()}
    with pytest.raises(FileExistsError, match="Chart output already exists"):
        export_charts(inputs, style=STYLE, output_root=root)
    assert list(modified.parent.iterdir()) == [modified]
    assert {path.name: path.read_bytes() for path in modified.iterdir()} == before


def test_export_rolls_back_a_failed_pair(control_path, tmp_path, monkeypatch):
    inputs = load_chart_inputs(control_path)
    root = tmp_path / "charts"
    original_link = os.link

    def fail_on_modified_metadata(source, target):
        if source.parent.name == "modified" and source.name == "rendering.json":
            raise OSError("simulated publication failure")
        original_link(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("rendering.export.os.link", fail_on_modified_metadata)
        with pytest.raises(OSError, match="simulated publication failure"):
            export_charts(inputs, style=STYLE, output_root=root)
    assert not [entry for entry in root.rglob("*") if entry.is_file()]
    outputs = export_charts(inputs, style=STYLE, output_root=root)
    assert len(outputs) == 2


def test_export_preserves_phase_two_directory(control_path):
    inputs = load_chart_inputs(control_path)
    with pytest.raises(ValueError, match="would modify the Phase-2 variant directory"):
        export_charts(inputs, style=STYLE, output_root=control_path.parent.parent)
    assert {path.name for path in control_path.iterdir()} == {
        "changes.parquet",
        "events.parquet",
        "manifest.json",
    }
