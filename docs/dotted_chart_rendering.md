# Phase 3 — Dotted Chart Rendering, Inspection & Diversification

Phase 3 draws Dotted Charts from saved [Phase-2 variants](pattern_injection.md).
The horizontal axis is absolute UTC, the vertical axis contains case rows, and
each event contributes one dot colored by activity.

## Load a saved variant and compare it in memory

Run this example from the repository root after an editable project install.

```python
from rendering.renderer import RenderStyle, render_charts
from rendering.views import load_chart_inputs

inputs = load_chart_inputs("data/processed/injected/bpic2012/gap_60c363dc8f11e86a")
charts = render_charts(inputs, role="both", style=RenderStyle())
for role, chart in charts.items():
    print(role, chart.counts, chart.diagnostics)
```

Use your saved variant path. Loading validates the three Phase-2 files, reads the
recorded Phase-1 Parquet and JSON provenance, and verifies the selected baseline.
The `all_complete_cases`, `sample_complete_cases`, and `explicit_complete_cases`
methods all use their recorded resolved case IDs. An empty injection recipe
gives identical baseline and modified event content. Relative Phase-1 paths
are interpreted from the working directory. Set
`source_root` on `load_chart_inputs()` when using a different working directory.

If either Phase-1 file is missing, use `role="modified"`. Case order and activity
colors then come from the complete modified log, recorded as `modified_fallback`.
An available source uses baseline order and colors for every render role. A
present source that fails validation raises an error. Loading verifies the
selected baseline with the same fingerprint used in Phase 2.

## Select and inspect views in Jupyter

With the project environment active, install the optional notebook tools and
open the notebook from the repository root.

```bash
python -m pip install --group notebook
jupyter lab notebooks/review_charts.ipynb
```

In the notebook, choose a discovered variant or set `variant_path`. Run the
load cell only when switching variants. Edit the `ViewSpec` and `RenderStyle`
settings, then run the view and display cells. The notebook displays the same
Agg canvas used by the API and supports baseline/modified panels side by side.
When the source is missing, it reports the fallback and displays the modified
chart. Routine inspection keeps all images in memory.

| `ViewSpec.mode` | Scope and options |
| --- | --- |
| `full` | Complete selected log across the union of both time ranges. |
| `time_window` | `start_utc` inclusive, `end_utc` exclusive, both explicitly UTC. |
| `focused` | A unique `injection_id` and/or `region_id` plus a positive `context`, such as `"12h"`. Pads the candidate interval or instant on both sides. |

Each of `case_ids` and `activities` accepts a list or tuple of exact values from
the variant. The renderer preserves all matching events, including partial
traces in a window. Time and activity filtering keep the union of cases with
events in either panel. Explicit case filters keep their requested rows even
when a row is blank. Case and activity filtering can reduce the observed
workload and remove events that contribute to a pattern candidate. A sampled
Phase-2 variant starts with fewer complete cases. Use full-log variants as
the basis for realistic workload density, including all matching events in
time-window views.

Filters preserve case order from the complete reference log. The notebook shows
selected counts, blank panels, and crowding diagnostics. Set
`show_candidate_regions=True` to project Phase-2 regions onto the modified
panel, including an empty Temporal Gap. Region overlays intersect the displayed
case rows and UTC axis. A region with `case_scope` set to `all` refers to all
cases of the saved variant. The cells list injection IDs and change counts.
Phase 4 verifies visible labels and boxes.

## Chart settings and density

Cases run from bottom to top by first baseline timestamp, with case ID resolving
ties. The full chart spans both frames. A constant full time range receives a
small amount of padding. Agg draws on a fixed plot rectangle at the configured
pixel dimensions and DPI. The defaults are 2400 × 1200 px,
200 DPI, a marker area of 3 points², alpha 0.6, the `turbo` palette, and a white
background. `legend=True` requests a legend in the reserved margin and reports
if it does not fit.

Charts retain every selected event and case row. Up to 15 evenly spaced case IDs
appear on the y-axis by default. Diagnostics report actual plot dimensions and
pixels per case row, and warn below 1 px per row. A dense full-log chart supports
global inspection and may have too little vertical resolution for localization.
Keep the recorded software versions and a consistent font environment for
byte-level reproducibility. Resolution and DPI change both chart geometry and
the marker footprint in pixels.

## Diversify with an explicit list of views

Load one variant as shown above, then select the configurations to inspect.
These examples use the saved full BPIC2012 Temporal Gap variant. Substitute
case IDs, activity names, UTC bounds, and region IDs for other variants.

```python
from rendering.views import ViewSpec

default = RenderStyle()
configurations = [
    (ViewSpec(), default),
    (
        ViewSpec(
            mode="time_window",
            start_utc="2012-01-23T08:00:00Z",
            end_utc="2012-01-24T08:00:00Z",
        ),
        RenderStyle(width_px=1800, height_px=1000, dpi=180),
    ),
    (
        ViewSpec(mode="focused", injection_id="inj_001", region_id="region_001", context="12h"),
        default,
    ),
    (ViewSpec(activities=["A_CANCELLED"]), RenderStyle(marker_size=4, alpha=0.75, legend=True)),
    (ViewSpec(case_ids=["182299", "203443"]), RenderStyle(palette="tab20")),
]
for view, style in configurations:
    charts = render_charts(inputs, view=view, style=style)
    print(view.mode, {role: chart.counts for role, chart in charts.items()})
```

To inspect Batching, open a saved `batch_*` variant in the notebook and choose
the relevant candidate. The same focused configuration accepts a batch instant
or interval. A narrower time window can improve horizontal readability while
preserving every matching event.

In the BPIC2012 pilot, the full view drew 262,200 events on 13,087 case rows
per panel. Its 960 px plot height gave 0.073 px per row. The 26-hour gap focus
used 505 rows and about 1.9 px per row, so adjacent markers could still overlap.
The activity-only `A_CANCELLED` view retained 2,807 rows. The two-case view
made individual rows easy to distinguish and showed 131 events. In a focused
sampled Batching view, 26 rows shared 760 px. Row spacing and time scope
describe chart readability. Phase 4 determines which patterns are visible.

## Explicit PNG and metadata export

Export a matched focused view from the repository root. Use your saved
variant's path and the injection and region IDs listed in its manifest.

```bash
python scripts/render_charts.py \
  --variant data/processed/injected/bpic2012/gap_60c363dc8f11e86a \
  --view focused --injection-id inj_001 --region-id region_001 \
  --context-hours 12 --role both --width-px 2400 --height-px 1200 --dpi 200
```

This activity-filtered window exports the modified role.

```bash
python scripts/render_charts.py \
  --variant data/processed/injected/bpic2012/gap_60c363dc8f11e86a \
  --view time_window --start-utc 2012-01-23T00:00:00Z --end-utc 2012-01-24T00:00:00Z \
  --activity A_CANCELLED --role modified
```

The CLI accepts `--role baseline`, `--role modified`, or `--role both` (default).
Use repeated `--case-id` and `--activity` flags for filters, and `--start-utc`
and `--end-utc` for time-window mode. `--output-root` overrides the default
`data/generated/charts` and `--source-root` anchors relative Phase-1 paths.
Run `python scripts/render_charts.py --help` for all style options. To export
from the notebook, set `export_role` and run the final cell. Both entry points
call `rendering.export.export_charts()`, which draws a clean image separately
from any inspection overlays.

Each export creates `chart.png` and `rendering.json` under
`data/generated/charts/<dataset_id>/<variant_id>/<chart_id>/`. Existing chart
directories are refused. The JSON identifies role, dataset, variant, and split
group and links the validated Phase-2 input with its content hashes and candidate
regions. It records the requested and resolved time scope, effective filters,
complete ordered case rows, color mapping and reference source, displayed ticks,
diagnostics, renderer versions, and a SHA-256 checksum of the PNG. Matched
charts share a `view_id`. A modified-only fallback has its own view identity.
The `chart_id` also incorporates role and input content identity.

## Phase-4 geometry and event inclusion

`geometry` records the actual Agg image dimensions, plot rectangle as
`[left, top, right, bottom]`, UTC and numerical x limits, and row-index y limits.
Coordinates are continuous pixels measured from the upper-left image edge. The
center of pixel `(column, row)` is `(column + 0.5, row + 0.5)`. The renderer
uses the drawn axes transform and flips the y origin. The complete ordered case
IDs in `view` map each case to its zero-based y-index. Export encodes the same
canvas at its original size. Tests check marker rasterization within 3 px near
axis edges, where clipping and antialiasing can affect colored pixels. The
mapping represents the dot center. Its precision is limited by the date
conversion and raster resolution. [Matplotlib transformations](https://matplotlib.org/stable/users/explain/artists/transforms_tutorial.html)

```python
import json

from rendering.geometry import PixelGeometry, data_to_pixel
from rendering.views import is_event_rendered, select_view

record = json.loads((exported_chart_dir / "rendering.json").read_text())
geometry = PixelGeometry.from_metadata(record)
x_px, y_px = data_to_pixel(timestamp_utc, case_id, geometry)
selected = select_view(inputs, view)
drawn = is_event_rendered(event_id, selected, role=record["role"])
```

For this example, `exported_chart_dir` is one exported chart path. Use the
original `ViewSpec` or recreate it from `record["view"]`. The saved
`requested_time_window_utc` gives `start_utc` and `end_utc` for a time window.
For focused mode, supply the saved injection/region IDs and convert `context_ns`
to `pd.Timedelta(..., unit="ns")`. The case and activity filters map to
`case_ids` and `activities` respectively. `data_to_pixel()` supports extrapolation
in time for displayed cases and raises for an unmapped case ID.
`is_event_rendered()` checks actual selection by stable event ID. Events with
the same case and time can differ in inclusion when activities are filtered.
Phase 4 assesses perceptual visibility and determines final bounding boxes.
