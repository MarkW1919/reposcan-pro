"""GPS provider helpers for live capture sources."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from reposcan_contracts.config.camera import CameraConfig, GpsProviderType
from reposcan_contracts.frame import GpsSnapshot


class GpsProviderError(RuntimeError):
    """Raised when a GPS provider cannot supply a snapshot."""


class TextLineReader(Protocol):
    def readline(self) -> str:
        ...

    def close(self) -> None:
        ...


def _parse_nmea_coordinate(raw_value: str, hemisphere: str) -> float | None:
    raw = raw_value.strip()
    hemi = hemisphere.strip().upper()
    if not raw or hemi not in {"N", "S", "E", "W"}:
        return None

    degree_digits = 2 if hemi in {"N", "S"} else 3
    if len(raw) < degree_digits + 3:
        return None

    try:
        degrees = float(raw[:degree_digits])
        minutes = float(raw[degree_digits:])
    except ValueError:
        return None

    value = degrees + (minutes / 60.0)
    if hemi in {"S", "W"}:
        value *= -1.0
    return value


def parse_nmea_sentence(sentence: str) -> GpsSnapshot | None:
    payload = sentence.strip()
    if not payload.startswith("$"):
        return None

    body = payload[1:].split("*", 1)[0]
    fields = body.split(",")
    if not fields:
        return None

    message_type = fields[0].upper()
    if message_type.endswith("RMC"):
        if len(fields) < 7 or fields[2] != "A":
            return None
        latitude = _parse_nmea_coordinate(fields[3], fields[4])
        longitude = _parse_nmea_coordinate(fields[5], fields[6])
        if latitude is None or longitude is None:
            return None
        return GpsSnapshot(latitude=latitude, longitude=longitude)

    if message_type.endswith("GGA"):
        if len(fields) < 6:
            return None
        try:
            fix_quality = int(fields[6] or "0")
        except ValueError:
            return None
        if fix_quality <= 0:
            return None
        latitude = _parse_nmea_coordinate(fields[2], fields[3])
        longitude = _parse_nmea_coordinate(fields[4], fields[5])
        if latitude is None or longitude is None:
            return None
        return GpsSnapshot(latitude=latitude, longitude=longitude)

    return None


class NmeaSerialLineReader:
    def __init__(self, serial_port: str, baud_rate: int, timeout_s: float) -> None:
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.timeout_s = timeout_s
        self._serial = None

    def _open_if_needed(self):
        if self._serial is not None:
            return self._serial
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise GpsProviderError("pyserial is required for gps.provider='nmea_serial'") from exc

        try:
            self._serial = serial.Serial(self.serial_port, baudrate=self.baud_rate, timeout=self.timeout_s)
        except Exception as exc:
            raise GpsProviderError(f"Unable to open GPS serial port '{self.serial_port}': {exc}") from exc
        return self._serial

    def readline(self) -> str:
        serial_handle = self._open_if_needed()
        try:
            raw = serial_handle.readline()
        except Exception as exc:
            raise GpsProviderError(f"Failed reading GPS serial port '{self.serial_port}': {exc}") from exc

        if isinstance(raw, bytes):
            return raw.decode("ascii", errors="ignore")
        return str(raw)

    def close(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.close()
        finally:
            self._serial = None


class NmeaSerialGpsProvider:
    def __init__(
        self,
        *,
        serial_port: str,
        baud_rate: int = 9600,
        timeout_s: float = 1.0,
        max_snapshot_age_s: float = 10.0,
        max_lines_per_poll: int = 5,
        line_reader_factory: Callable[[str, int, float], TextLineReader] | None = None,
    ) -> None:
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.timeout_s = timeout_s
        self.max_snapshot_age_s = max_snapshot_age_s
        self.max_lines_per_poll = max_lines_per_poll
        self._line_reader_factory = line_reader_factory or NmeaSerialLineReader
        self._reader: TextLineReader | None = None
        self._last_snapshot: GpsSnapshot | None = None
        self._last_snapshot_at: datetime | None = None

    def _get_line_reader(self) -> TextLineReader:
        if self._reader is None:
            try:
                self._reader = self._line_reader_factory(self.serial_port, self.baud_rate, self.timeout_s)
            except GpsProviderError:
                raise
            except Exception as exc:
                raise GpsProviderError(
                    f"Unable to initialize GPS provider for serial port '{self.serial_port}': {exc}"
                ) from exc
        return self._reader

    def _cached_snapshot(self) -> GpsSnapshot | None:
        if self._last_snapshot is None or self._last_snapshot_at is None:
            return None
        if datetime.now(timezone.utc) - self._last_snapshot_at > timedelta(seconds=self.max_snapshot_age_s):
            return None
        return self._last_snapshot

    def current_snapshot(self) -> GpsSnapshot | None:
        line_reader = self._get_line_reader()
        for _ in range(self.max_lines_per_poll):
            line = line_reader.readline()
            if not line:
                break
            snapshot = parse_nmea_sentence(line)
            if snapshot is None:
                continue
            self._last_snapshot = snapshot
            self._last_snapshot_at = datetime.now(timezone.utc)
            return snapshot
        return self._cached_snapshot()

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None


def build_gps_provider(
    camera: CameraConfig,
    *,
    line_reader_factory: Callable[[str, int, float], TextLineReader] | None = None,
):
    if camera.gps.provider == GpsProviderType.disabled:
        return None

    if camera.gps.provider == GpsProviderType.nmea_serial:
        return NmeaSerialGpsProvider(
            serial_port=str(camera.gps.serial_port),
            baud_rate=camera.gps.baud_rate,
            timeout_s=camera.gps.timeout_s,
            max_snapshot_age_s=camera.gps.max_snapshot_age_s,
            line_reader_factory=line_reader_factory,
        )

    raise GpsProviderError(f"Unsupported GPS provider '{camera.gps.provider.value}'")
