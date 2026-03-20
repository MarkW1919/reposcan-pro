"""Capture source primitives for camera and file-backed test ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

from reposcan_contracts.frame import GpsSnapshot


def _parse_utc_timestamp(timestamp_utc: str) -> datetime:
    return datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CapturedFrame:
    frame_path: Path
    timestamp_utc: str
    frame_number: int
    sequence_id: str | None = None
    gps_snapshot: GpsSnapshot | None = None


class FileSequenceFrameSource(Iterable[CapturedFrame]):
    """Deterministic file-backed frame source for local development and tests."""

    def __init__(
        self,
        frame_paths: list[Path],
        *,
        start_timestamp_utc: str,
        frame_interval_ms: float = 33.3,
        start_frame_number: int = 0,
        sequence_id: str | None = None,
        gps_snapshot: GpsSnapshot | None = None,
    ) -> None:
        if frame_interval_ms <= 0:
            raise ValueError("frame_interval_ms must be greater than zero")

        self.frame_paths = frame_paths
        self.start_timestamp_utc = start_timestamp_utc
        self.frame_interval_ms = frame_interval_ms
        self.start_frame_number = start_frame_number
        self.sequence_id = sequence_id
        self.gps_snapshot = gps_snapshot

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        glob_pattern: str = "*.jpg",
        start_timestamp_utc: str,
        frame_interval_ms: float = 33.3,
        start_frame_number: int = 0,
        sequence_id: str | None = None,
        gps_snapshot: GpsSnapshot | None = None,
    ) -> "FileSequenceFrameSource":
        root = Path(directory)
        frame_paths = sorted(path for path in root.glob(glob_pattern) if path.is_file())
        return cls(
            frame_paths,
            start_timestamp_utc=start_timestamp_utc,
            frame_interval_ms=frame_interval_ms,
            start_frame_number=start_frame_number,
            sequence_id=sequence_id,
            gps_snapshot=gps_snapshot,
        )

    def __iter__(self) -> Iterator[CapturedFrame]:
        start_time = _parse_utc_timestamp(self.start_timestamp_utc)
        delta = timedelta(milliseconds=self.frame_interval_ms)

        for index, frame_path in enumerate(self.frame_paths):
            timestamp_utc = _format_utc_timestamp(start_time + (delta * index))
            yield CapturedFrame(
                frame_path=frame_path,
                timestamp_utc=timestamp_utc,
                frame_number=self.start_frame_number + index,
                sequence_id=self.sequence_id,
                gps_snapshot=self.gps_snapshot,
            )
