"""Geometry of the final Agg raster, independent of rendered-event membership."""

from dataclasses import dataclass
from functools import cached_property
from typing import TypedDict

import pandas as pd
from matplotlib import dates
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg

from data.pattern_injection.engine import utc_timestamp

RENDERING_SCHEMA_VERSION = 1
NANOSECONDS_PER_DAY = 86_400_000_000_000


class GeometryRecord(TypedDict):
    """Serializable geometry for a linear UTC x-axis and compact case rows."""

    width_px: int
    height_px: int
    origin: str
    pixel_reference: str
    plot_rect_px: list[float]
    xlim_utc: list[str]
    xlim_date_num: list[float]
    ylim_index: list[float]
    time_origin_utc: str | None
    matplotlib_date_epoch: str | None


@dataclass(frozen=True)
class PixelGeometry:
    """Pixel transform and the complete ordered case IDs for one chart."""

    record: GeometryRecord
    ordered_case_ids: tuple[str, ...]

    @cached_property
    def _case_rows(self) -> dict[str, int]:
        return {case_id: row for row, case_id in enumerate(self.ordered_case_ids)}

    @classmethod
    def from_metadata(cls, metadata: dict) -> "PixelGeometry":
        """Restore the transform from an exported ``rendering.json`` record."""
        if metadata.get("schema_version") != RENDERING_SCHEMA_VERSION:
            raise ValueError("Unsupported rendering metadata schema_version")
        view = metadata["view"]
        return cls(metadata["geometry"], tuple(view["ordered_case_ids"]))


def _date_coordinates(values, origin: pd.Timestamp | None):
    if origin is None:
        return dates.date2num(values)
    return (values - origin.to_datetime64()).astype("int64") / NANOSECONDS_PER_DAY


def capture_geometry(
    axes: Axes,
    canvas: FigureCanvasAgg,
    time_bounds: tuple[pd.Timestamp, pd.Timestamp],
    ordered_case_ids: tuple[str, ...],
    time_origin: pd.Timestamp | None,
) -> PixelGeometry:
    """Capture the linear transform from the drawn, export-resolution canvas."""
    width, height = canvas.get_width_height()
    xmin, xmax = axes.get_xlim()
    ymin, ymax = axes.get_ylim()
    (left, bottom), (right, top) = axes.transData.transform(((xmin, ymin), (xmax, ymax)))
    return PixelGeometry(
        {
            "width_px": width,
            "height_px": height,
            "origin": "top_left",
            "pixel_reference": "edges",
            "plot_rect_px": [
                float(left),
                height - float(top),
                float(right),
                height - float(bottom),
            ],
            "xlim_utc": [time.isoformat() for time in time_bounds],
            "xlim_date_num": [float(xmin), float(xmax)],
            "ylim_index": [float(ymin), float(ymax)],
            "time_origin_utc": time_origin.isoformat() if time_origin is not None else None,
            "matplotlib_date_epoch": dates.get_epoch() if time_origin is None else None,
        },
        ordered_case_ids,
    )


def _stored_date_coordinate(timestamp: pd.Timestamp, record: GeometryRecord) -> float:
    if record["time_origin_utc"] is not None:
        origin = pd.Timestamp(record["time_origin_utc"])
        # Python integers also support extrapolation far outside a short view.
        return (timestamp.value - origin.value) / NANOSECONDS_PER_DAY
    epoch = record["matplotlib_date_epoch"]
    if epoch == dates.get_epoch():
        return float(_date_coordinates(timestamp.to_datetime64(), None))
    # Apply Matplotlib's date-number convention with the original epoch, which
    # can differ from the epoch initialized in the current Python process.
    seconds, nanoseconds = divmod(timestamp.value, 1_000_000_000)
    epoch_seconds = int(pd.Timestamp(epoch).as_unit("s").asm8.astype("int64"))
    return (float(seconds - epoch_seconds) + nanoseconds / 1_000_000_000) / 86_400


def data_to_pixel(
    timestamp_utc: str | pd.Timestamp, case_id: str, geometry: PixelGeometry
) -> tuple[float, float]:
    """Map UTC and a displayed case to continuous, top-left PNG pixel coordinates.

    Integer coordinates mark pixel edges. Pixel (column, row) has its center at
    (column + 0.5, row + 0.5). Coordinates extrapolate beyond the plot limits.
    This transform describes positions independently of which events were drawn.
    """
    try:
        row = geometry._case_rows[case_id]
    except KeyError as error:
        raise ValueError(f"Case ID {case_id!r} has no displayed row in this chart") from error
    timestamp = utc_timestamp(timestamp_utc, "timestamp_utc")
    record = geometry.record
    x = _stored_date_coordinate(timestamp, record)
    xmin, xmax = record["xlim_date_num"]
    ymin, ymax = record["ylim_index"]
    left, top, right, bottom = record["plot_rect_px"]
    return (
        left + (x - xmin) / (xmax - xmin) * (right - left),
        bottom - (row - ymin) / (ymax - ymin) * (bottom - top),
    )
