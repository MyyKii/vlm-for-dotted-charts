"""Configuration shared by event-log loading and preprocessing."""

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CASE_ID_COLUMN = "case:concept:name"
ACTIVITY_COLUMN = "concept:name"
TIMESTAMP_COLUMN = "time:timestamp"
REQUIRED_COLUMNS = (CASE_ID_COLUMN, ACTIVITY_COLUMN, TIMESTAMP_COLUMN)


@dataclass(frozen=True)
class EventLogConfig:
    """Describe a local XES/CSV source without requiring it to exist yet.

    Infer the format from the suffix unless explicitly provided. Naive timestamps
    require ``source_timezone``; aware timestamps retain their instant in UTC.
    ``timestamp_format=None`` means ISO 8601, avoiding ambiguous date inference.
    """

    input_path: Path | str
    file_format: str | None = None
    case_id_column: str = CASE_ID_COLUMN
    activity_column: str = ACTIVITY_COLUMN
    timestamp_column: str = TIMESTAMP_COLUMN
    csv_separator: str = ","
    timestamp_format: str | None = None
    source_timezone: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.input_path, (str, Path)) or not str(self.input_path).strip():
            raise ValueError("input_path must be a nonempty file path")
        path = Path(self.input_path)
        if not path.name:
            raise ValueError("input_path must name a file")
        object.__setattr__(self, "input_path", path)

        file_format = self.file_format
        if file_format is None:
            file_format = path.suffix.lstrip(".")
        if not isinstance(file_format, str) or file_format.lower() not in {"xes", "csv"}:
            raise ValueError("file_format must be 'xes' or 'csv' (or inferred from the suffix)")
        object.__setattr__(self, "file_format", file_format.lower())

        columns = (self.case_id_column, self.activity_column, self.timestamp_column)
        for field, column in zip(
            ("case_id_column", "activity_column", "timestamp_column"), columns, strict=True
        ):
            if not isinstance(column, str) or not column.strip():
                raise ValueError(f"{field} must be a nonempty column name")
        if len(set(columns)) != len(columns):
            raise ValueError("Case ID, activity, and timestamp columns must be distinct")

        if (
            not isinstance(self.csv_separator, str)
            or len(self.csv_separator) != 1
            or self.csv_separator in {"\n", "\r"}
        ):
            raise ValueError("csv_separator must be a single character other than a newline")
        if self.timestamp_format is not None and (
            not isinstance(self.timestamp_format, str) or not self.timestamp_format.strip()
        ):
            raise ValueError("timestamp_format must be a nonempty format string or None")
        if self.source_timezone is not None:
            if not isinstance(self.source_timezone, str) or not self.source_timezone.strip():
                raise ValueError("source_timezone must be an IANA timezone name or None")
            try:
                ZoneInfo(self.source_timezone)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError(f"Unknown source_timezone: {self.source_timezone!r}") from error
