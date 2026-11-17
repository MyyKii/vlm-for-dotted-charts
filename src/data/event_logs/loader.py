"""Read local event logs without normalizing timestamps or removing records."""

import warnings
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
import pm4py

from data.event_logs.config import EventLogConfig
from data.event_logs.preprocessing import standardize_columns


def _xes_timestamps(path: Path, timestamp_column: str) -> list[str | None]:
    """Retain timestamp text: PM4Py otherwise interprets naive XES dates as UTC."""
    timestamps = []
    with path.open("rb") as source:
        context = ElementTree.iterparse(source, events=("start", "end"))
        _, root = next(context)
        if root.tag.rsplit("}", 1)[-1] != "log":
            raise ValueError("XES input must have a <log> root element")
        for event, element in context:
            tag = element.tag.rsplit("}", 1)[-1]
            if event == "end" and tag == "event":
                timestamps.append(
                    next(
                        (
                            child.get("value")
                            for child in element
                            if child.get("key") == timestamp_column
                        ),
                        None,
                    )
                )
                element.clear()
            elif event == "end" and tag == "trace":
                element.clear()
    return timestamps


def load_event_log(config: EventLogConfig) -> pd.DataFrame:
    """Load a CSV/XES file with standard names and all additional event columns.

    Required CSV identifiers are read as strings, preserving leading zeros and
    literal ``NA`` values. Empty fields/rows remain for subsequent validation.
    Timestamp parsing, UTC normalization, and ordering belong to preprocessing.
    XES timestamps retain their source text to avoid implicit timezone guesses.
    """
    path = Path(config.input_path)
    if path.suffix.lower() != f".{config.file_format}":
        raise ValueError(f"Input extension {path.suffix!r} does not match {config.file_format!r}")
    if not path.exists():
        raise FileNotFoundError(f"Event-log file not found: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"Event-log input is not a file: {path}")

    try:
        if config.file_format == "csv":
            with warnings.catch_warnings():
                warnings.simplefilter("error", pd.errors.ParserWarning)
                frame = pd.read_csv(
                    path,
                    sep=config.csv_separator,
                    dtype={
                        config.case_id_column: "string",
                        config.activity_column: "string",
                        config.timestamp_column: "string",
                        "identity:id": "string",
                    },
                    keep_default_na=False,
                    skip_blank_lines=False,
                    index_col=False,
                )
        else:
            timestamps = _xes_timestamps(path, config.timestamp_column)
            frame = pm4py.read_xes(
                str(path),
                variant="iterparse",
                return_legacy_log_object=False,
                timestamp_sort=False,
                show_progress_bar=False,
            )
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("pm4py.read_xes() must return a Pandas DataFrame")
            if len(frame) != len(timestamps):
                raise ValueError("XES loading unexpectedly changed the number of events")
            if any(value is not None for value in timestamps):
                frame[config.timestamp_column] = timestamps
    except (ValueError, SyntaxError, pd.errors.ParserWarning) as error:
        raise ValueError(
            f"Unable to parse {config.file_format.upper()} event log {path}: {error}"
        ) from error

    # format_dataframe() can drop invalid rows and guess timezones. Apply only
    # the structural mapping here, leaving all records for explicit validation.
    return standardize_columns(frame, config)
