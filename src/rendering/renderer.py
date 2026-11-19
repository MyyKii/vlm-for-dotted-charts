"""Draw one fixed-semantics Dotted Chart on an export-resolution Agg canvas."""

import math
from dataclasses import dataclass
from datetime import timezone
from io import BytesIO
from threading import Lock

import matplotlib as mpl
import pandas as pd
from matplotlib import dates
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_hex, to_rgba_array
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PIL import Image

from data.event_logs.config import ACTIVITY_COLUMN, CASE_ID_COLUMN, TIMESTAMP_COLUMN
from data.event_logs.preprocessing import EVENT_ID_COLUMN, SOURCE_ROW_COLUMN
from rendering.geometry import PixelGeometry, _date_coordinates, capture_geometry
from rendering.views import (
    ChartInputs,
    ChartRole,
    EffectiveView,
    RenderRole,
    ViewSpec,
    candidate_regions,
    chart_roles,
    region_time_bounds,
    select_view,
)

AXES_RECT = (0.13, 0.15, 0.65, 0.8)  # left, bottom, width, height in figure fractions
LEGEND_LEFT = 0.79
MAX_TIME_TICK_LABELS = 6
_DRAW_LOCK = Lock()


@dataclass(frozen=True)
class RenderStyle:
    """Pixel dimensions, DPI, and a small set of reproducible style controls."""

    width_px: int = 2400
    height_px: int = 1200
    dpi: int = 200
    marker_size: float = 3.0  # scatter area in points squared
    alpha: float = 0.6
    palette: str = "turbo"
    legend: bool = False
    background: str = "#ffffff"
    max_case_tick_labels: int = 15

    def __post_init__(self) -> None:
        for field in ("width_px", "height_px", "dpi"):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field} must be a positive integer")
        for field in ("marker_size", "alpha"):
            value = getattr(self, field)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{field} must be a finite number")
            object.__setattr__(self, field, float(value))
        if self.marker_size <= 0 or not 0 <= self.alpha <= 1:
            raise ValueError("marker_size must be positive and alpha must be between 0 and 1")
        if not isinstance(self.palette, str) or self.palette not in mpl.colormaps:
            raise ValueError(f"Unknown Matplotlib palette {self.palette!r}")
        if type(self.max_case_tick_labels) is not int or self.max_case_tick_labels < 0:
            raise ValueError("max_case_tick_labels must be a nonnegative integer")
        if type(self.legend) is not bool:
            raise ValueError("legend must be a boolean")
        try:
            background = to_hex(self.background, keep_alpha=True)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid chart background {self.background!r}") from error
        object.__setattr__(self, "background", background)


@dataclass(frozen=True)
class ChartCounts:
    """Role-specific event counts and shared case-row density on the actual axes."""

    events: int
    cases: int
    activities: int
    plot_width_px: float
    plot_height_px: float
    pixels_per_case_row: float | None


@dataclass(frozen=True)
class RenderedChart:
    """A drawn in-memory chart and its shared selection and diagnostics."""

    canvas: FigureCanvasAgg
    role: ChartRole
    view: EffectiveView
    geometry: PixelGeometry
    activity_colors: dict[str, str]
    case_ticks: tuple[int, ...]
    legend_displayed: bool
    counts: ChartCounts
    diagnostics: tuple[str, ...]

    def png_bytes(self) -> bytes:
        """Encode the exact drawn Agg pixels as a PNG in memory."""
        dpi = self.canvas.figure.dpi
        with (
            BytesIO() as output,
            Image.frombuffer(
                "RGBA",
                self.canvas.get_width_height(),
                self.canvas.buffer_rgba(),
                "raw",
                "RGBA",
                0,
                1,
            ) as image,
        ):
            image.save(output, format="PNG", dpi=(dpi, dpi))
            return output.getvalue()


def _inches(pixels: int, dpi: int) -> float:
    inches = pixels / dpi
    # Agg truncates pixel dimensions. Guard against a product one ULP below target.
    return math.nextafter(inches, math.inf) if inches * dpi < pixels else inches


def _even_indices(size: int, maximum: int) -> tuple[int, ...]:
    count = min(size, maximum)
    if count < 2:
        return ((size - 1) // 2,) if count else ()
    return tuple(round(index * (size - 1) / (count - 1)) for index in range(count))


def _activity_colors(activities: tuple[str, ...], palette: str) -> dict[str, str]:
    cmap = mpl.colormaps[palette]
    denominator = max(1, len(activities) - 1)
    return {name: to_hex(cmap(index / denominator)) for index, name in enumerate(activities)}


def _configure_time_axis(axes: Axes, view: EffectiveView) -> pd.Timestamp | None:
    start, end = view.time_bounds
    if end.value - start.value < 1_000_000_000:
        # Small intervals need a nearby origin to preserve distinct date coordinates.
        times = (start, end)
        limits = [_date_coordinates(time.to_datetime64(), start) for time in times]
        labels = [time.isoformat().removesuffix("+00:00").replace("T", "\n") for time in times]
        axes.set_xticks(limits, labels)
        axes.set_xlim(limits)
        return start

    limits = [dates.date2num(time.to_datetime64()) for time in view.time_bounds]
    locator = dates.AutoDateLocator(tz=timezone.utc, minticks=3, maxticks=MAX_TIME_TICK_LABELS)
    ticks = locator.tick_values(start.to_pydatetime(warn=False), end.to_pydatetime(warn=False))
    shown = [tick for tick in ticks if limits[0] <= tick <= limits[1]] or limits
    axes.set_xticks([shown[index] for index in _even_indices(len(shown), MAX_TIME_TICK_LABELS)])
    axes.xaxis.set_major_formatter(dates.ConciseDateFormatter(locator, tz=timezone.utc))
    axes.set_xlim(limits)
    return None


def _draw(
    view: EffectiveView,
    style: RenderStyle,
    role: ChartRole,
    colors: dict[str, str],
    legend_colors: dict[str, str],
    overlays: list[tuple[str, dict]],
) -> RenderedChart:
    figure = Figure(
        figsize=(_inches(style.width_px, style.dpi), _inches(style.height_px, style.dpi)),
        dpi=style.dpi,
        facecolor=style.background,
        layout="none",
    )
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_axes(AXES_RECT, facecolor=style.background)
    font_size = min(style.width_px, style.height_px) * 0.016 * 72 / style.dpi
    rows = {case_id: index for index, case_id in enumerate(view.ordered_case_ids)}
    row_count = len(rows)
    ticks = _even_indices(row_count, style.max_case_tick_labels)
    axes.set_yticks(ticks, [view.ordered_case_ids[row] for row in ticks])
    axes.set_ylim(-0.5, max(1, row_count) - 0.5)
    axes.set_ylabel("Case ID", fontsize=font_size)
    axes.set_xlabel("Timestamp (UTC)", fontsize=font_size)
    axes.tick_params(labelsize=font_size * 0.85)
    axes.xaxis.offsetText.set_fontsize(font_size * 0.85)
    origin = _configure_time_axis(axes, view)

    events = view.events(role).sort_values([TIMESTAMP_COLUMN, SOURCE_ROW_COLUMN, EVENT_ID_COLUMN])
    _scatter(axes, events, rows, style, colors, origin)
    _draw_candidate_regions(axes, rows, view.time_bounds, origin, overlays)
    legend = None
    if legend_colors:
        handles = [
            Line2D([], [], marker="o", linestyle="none", color=color, label=label)
            for label, color in legend_colors.items()
        ]
        legend = figure.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(LEGEND_LEFT, 0.95),
            fontsize=font_size * 0.8,
            markerscale=font_size / 8,
            frameon=False,
        )
    canvas.draw()

    diagnostics = []
    if legend is not None:
        extent = legend.get_window_extent()
        if extent.x1 > style.width_px * 0.99 or extent.y0 < style.height_px * 0.05:
            legend.remove()
            legend = None
            canvas.draw()
            diagnostics.append("Legend does not fit in the reserved margin.")
    geometry = capture_geometry(axes, canvas, view.time_bounds, view.ordered_case_ids, origin)
    left, top, right, bottom = geometry.record["plot_rect_px"]
    plot_width, plot_height = right - left, bottom - top
    pixels_per_row = plot_height / row_count if row_count else None
    if pixels_per_row is not None and pixels_per_row < 1:
        diagnostics.append(f"Case rows are compressed to {pixels_per_row:.3f} px per row.")
    if events.empty:
        diagnostics.append(f"No {role} events match this view.")
    counts = ChartCounts(
        len(events),
        row_count,
        int(events[ACTIVITY_COLUMN].nunique()),
        plot_width,
        plot_height,
        pixels_per_row,
    )
    return RenderedChart(
        canvas, role, view, geometry, colors, ticks, legend is not None, counts, tuple(diagnostics)
    )


def _scatter(
    axes: Axes,
    events: pd.DataFrame,
    rows: dict[str, int],
    style: RenderStyle,
    colors: dict[str, str],
    origin: pd.Timestamp | None,
) -> None:
    if events.empty:
        return
    color_indices = pd.Categorical(events[ACTIVITY_COLUMN], categories=list(colors)).codes
    axes.scatter(
        _date_coordinates(events[TIMESTAMP_COLUMN].to_numpy(dtype="datetime64[ns]"), origin),
        events[CASE_ID_COLUMN].map(rows),
        c=to_rgba_array(list(colors.values()))[color_indices],
        s=style.marker_size,
        alpha=style.alpha,
        marker="o",
        linewidths=0,
        edgecolors="none",
    )


def _draw_candidate_regions(
    axes: Axes,
    rows: dict[str, int],
    bounds: tuple[pd.Timestamp, pd.Timestamp],
    origin: pd.Timestamp | None,
    overlays: list[tuple[str, dict]],
) -> None:
    for _, region in overlays:
        start, end = region_time_bounds(region)
        instant = start == end
        if instant:
            if not bounds[0] <= start <= bounds[1]:
                continue
        else:
            start, end = max(start, bounds[0]), min(end, bounds[1])
            if start >= end:
                continue
        left, right = [_date_coordinates(time.to_datetime64(), origin) for time in (start, end)]
        scope = region["case_scope"]
        if scope["type"] == "all":
            if instant:
                axes.axvline(left, color="#424242", linestyle="--")
            else:
                axes.axvspan(left, right, facecolor="#ffbf00", alpha=0.2)
        else:
            selected_rows = [rows[case_id] for case_id in scope["case_ids"] if case_id in rows]
            if instant:
                axes.vlines(
                    left,
                    [row - 0.4 for row in selected_rows],
                    [row + 0.4 for row in selected_rows],
                    color="#424242",
                )
            else:
                axes.hlines(selected_rows, left, right, color="#424242", linestyle="--")


def render_charts(
    inputs: ChartInputs,
    *,
    view: ViewSpec = ViewSpec(),
    role: RenderRole = "both",
    style: RenderStyle = RenderStyle(),
    show_candidate_regions: bool = False,
) -> dict[ChartRole, RenderedChart]:
    """Draw a chart or matched pair in memory; candidate overlays are opt-in."""
    roles = chart_roles(inputs, role)
    selected = select_view(inputs, view)
    colors = _activity_colors(selected.reference_activities, style.palette)
    legend_colors = {}
    if style.legend:
        activities = set(selected.modified[ACTIVITY_COLUMN].unique())
        if selected.baseline is not None:
            activities.update(selected.baseline[ACTIVITY_COLUMN].unique())
        legend_colors = {name: color for name, color in colors.items() if name in activities}
    overlays = candidate_regions(inputs) if show_candidate_regions else []
    # Matplotlib's temporary rc settings are process-wide.
    with _DRAW_LOCK, mpl.rc_context(rc=mpl.rcParamsDefault):
        mpl.rcParams["text.parse_math"] = False  # Case and activity labels are literal IDs.
        return {
            item: _draw(
                selected, style, item, colors, legend_colors, overlays if item == "modified" else []
            )
            for item in roles
        }
