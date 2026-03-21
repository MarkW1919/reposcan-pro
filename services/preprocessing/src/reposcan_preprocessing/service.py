"""Preprocessing service for low-light-oriented frame conditioning."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import NightModePolicy, PipelineConfig
from reposcan_contracts.frame import FrameEnvelope, PreparedFrame, PreprocessingMetadata


class PreprocessingService:
    def __init__(
        self,
        pipeline_config: PipelineConfig,
        *,
        artifact_root: str | Path = "runtime/preprocessed",
    ) -> None:
        self.pipeline_config = pipeline_config
        self.artifact_root = Path(artifact_root)

    @classmethod
    def from_config_path(
        cls,
        config_path: str = "configs/pipelines/default-edge.yaml",
        *,
        artifact_root: str | Path = "runtime/preprocessed",
    ) -> "PreprocessingService":
        return cls(load_pipeline_config(config_path), artifact_root=artifact_root)

    def prepare(self, frame: FrameEnvelope) -> PreparedFrame:
        config = self.pipeline_config.preprocessing
        if not config.enabled:
            return self._passthrough(frame)

        source_path = Path(frame.frame_path)
        if not source_path.exists():
            return self._passthrough(frame)

        try:
            with Image.open(source_path) as source_image:
                working_image = source_image.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError):
            return self._passthrough(frame)

        brightness_before = self._mean_brightness(working_image)
        night_mode = self._night_mode_triggered(frame, brightness_before)
        prepared_image = working_image
        denoise_applied = False
        contrast_enhanced = False

        if config.denoise:
            filter_size = self._median_filter_size()
            if filter_size > 1:
                prepared_image = prepared_image.filter(ImageFilter.MedianFilter(size=filter_size))
                denoise_applied = True

        if config.contrast_enhancement:
            prepared_image = self._enhance_contrast(prepared_image, night_mode=night_mode)
            contrast_enhanced = True

        brightness_after = self._mean_brightness(prepared_image)
        prepared_frame_path = self._artifact_path(frame, source_path)
        prepared_frame_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs: dict = {}
        if prepared_frame_path.suffix.lower() in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 90
        prepared_image.save(prepared_frame_path, **save_kwargs)

        return PreparedFrame(
            frame_id=frame.frame_id,
            camera_id=frame.camera_id,
            timestamp_utc=frame.timestamp_utc,
            raw_frame_path=frame.frame_path,
            prepared_frame_path=str(prepared_frame_path),
            frame_number=frame.frame_number,
            source_type=frame.source_type,
            camera_profile=frame.camera_profile,
            gps_snapshot=frame.gps_snapshot,
            sequence_id=frame.sequence_id,
            preprocessing=PreprocessingMetadata(
                artifact_generated=True,
                denoise_applied=denoise_applied,
                contrast_enhanced=contrast_enhanced,
                night_mode_triggered=night_mode,
                mean_brightness_before=brightness_before,
                mean_brightness_after=brightness_after,
            ),
        )

    def _passthrough(self, frame: FrameEnvelope) -> PreparedFrame:
        return PreparedFrame(
            frame_id=frame.frame_id,
            camera_id=frame.camera_id,
            timestamp_utc=frame.timestamp_utc,
            raw_frame_path=frame.frame_path,
            prepared_frame_path=frame.frame_path,
            frame_number=frame.frame_number,
            source_type=frame.source_type,
            camera_profile=frame.camera_profile,
            gps_snapshot=frame.gps_snapshot,
            sequence_id=frame.sequence_id,
        )

    def _artifact_path(self, frame: FrameEnvelope, source_path: Path) -> Path:
        suffix = source_path.suffix or ".jpg"
        sequence = frame.sequence_id or "adhoc"
        return self.artifact_root / frame.camera_id / sequence / f"{frame.frame_id}_prepared{suffix}"

    def _mean_brightness(self, image: Image.Image) -> float:
        grayscale = ImageOps.grayscale(image)
        return float(ImageStat.Stat(grayscale).mean[0])

    def _night_mode_triggered(self, frame: FrameEnvelope, brightness_before: float) -> bool:
        config = self.pipeline_config.preprocessing
        if config.ir_night_mode == NightModePolicy.always:
            return True
        if config.ir_night_mode == NightModePolicy.never:
            return False

        if frame.camera_profile.ir_mode:
            return True

        lux_threshold = config.night_mode_threshold_lux or 0.0
        # Map the config's lux-oriented night threshold into a simple pixel-brightness
        # heuristic so we can make low-light decisions without a dedicated lux sensor.
        brightness_threshold = min(max(lux_threshold * 8.0, 0.0), 255.0)
        return brightness_before <= brightness_threshold

    def _median_filter_size(self) -> int:
        strength = self.pipeline_config.preprocessing.denoise_strength
        if strength >= 0.8:
            return 5
        if strength >= 0.35:
            return 3
        return 1

    def _enhance_contrast(self, image: Image.Image, *, night_mode: bool) -> Image.Image:
        clip_cutoff = min(max(self.pipeline_config.preprocessing.contrast_clip_limit * 1.5, 0.0), 10.0)
        if night_mode:
            grayscale = ImageOps.grayscale(image)
            lifted = ImageEnhance.Brightness(grayscale).enhance(1.15)
            return ImageOps.autocontrast(ImageOps.equalize(lifted), cutoff=clip_cutoff).convert("RGB")
        return ImageOps.autocontrast(image, cutoff=clip_cutoff)
