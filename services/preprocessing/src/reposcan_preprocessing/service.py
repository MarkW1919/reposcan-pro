"""Preprocessing service for low-light-oriented frame conditioning."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import NightModePolicy, PipelineConfig, PreprocessingBackend
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
        enhancement_backend = self._selected_backend()
        prepared_image = working_image
        denoise_applied = False
        exposure_adjusted = False
        contrast_enhanced = False
        clahe_applied = False

        if config.exposure_compensation:
            prepared_image, exposure_adjusted = self._adjust_exposure(
                prepared_image,
                brightness_before=brightness_before,
                night_mode=night_mode,
            )

        if config.denoise:
            prepared_image, denoise_applied = self._denoise(
                prepared_image,
                backend=enhancement_backend,
            )

        if config.contrast_enhancement:
            prepared_image, clahe_applied = self._enhance_contrast(
                prepared_image,
                backend=enhancement_backend,
                night_mode=night_mode,
            )
            contrast_enhanced = True

        brightness_after = self._mean_brightness(prepared_image)
        prepared_frame_path = self._artifact_path(frame, source_path)
        prepared_frame_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs: dict[str, int] = {}
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
                enhancement_backend=enhancement_backend.value,
                denoise_applied=denoise_applied,
                exposure_adjusted=exposure_adjusted,
                contrast_enhanced=contrast_enhanced,
                clahe_applied=clahe_applied,
                night_mode_triggered=night_mode,
                mean_brightness_before=brightness_before,
                mean_brightness_after=brightness_after,
            ),
        )

    def prepare_plate_crop(
        self,
        crop_source: str | Path | Image.Image,
        *,
        corners: Sequence[tuple[float, float]] | None = None,
        output_size: tuple[int, int] = (160, 48),
    ) -> Image.Image:
        image = self._load_image(crop_source)
        if corners and self.pipeline_config.preprocessing.rectify_plate_crops:
            image = self.rectify_plate_crop(image, corners=corners, output_size=output_size)

        brightness_before = self._mean_brightness(image)
        backend = self._selected_backend()
        night_mode = brightness_before <= self.pipeline_config.preprocessing.target_mean_brightness

        if self.pipeline_config.preprocessing.exposure_compensation:
            image, _ = self._adjust_exposure(image, brightness_before=brightness_before, night_mode=night_mode)
        if self.pipeline_config.preprocessing.denoise:
            image, _ = self._denoise(image, backend=backend)
        if self.pipeline_config.preprocessing.contrast_enhancement:
            image, _ = self._enhance_contrast(image, backend=backend, night_mode=night_mode)
        return image

    def rectify_plate_crop(
        self,
        image: Image.Image,
        *,
        corners: Sequence[tuple[float, float]],
        output_size: tuple[int, int] = (160, 48),
    ) -> Image.Image:
        if len(corners) != 4:
            raise ValueError("Plate crop rectification requires exactly four corner points")

        backend = self._selected_backend()
        if backend == PreprocessingBackend.opencv:
            cv2_module = self._cv2()
            if cv2_module is not None:
                return self._rectify_with_opencv(image, corners=corners, output_size=output_size)
        return self._rectify_with_pillow(image, corners=corners, output_size=output_size)

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
        brightness_threshold = min(max(lux_threshold * 8.0, 0.0), 255.0)
        return brightness_before <= brightness_threshold

    def _selected_backend(self) -> PreprocessingBackend:
        configured = self.pipeline_config.preprocessing.enhancement_backend
        opencv_available = self._cv2() is not None and self._numpy() is not None
        if configured == PreprocessingBackend.auto:
            return PreprocessingBackend.opencv if opencv_available else PreprocessingBackend.pillow
        if configured == PreprocessingBackend.opencv and not opencv_available:
            return PreprocessingBackend.pillow
        return configured

    def _median_filter_size(self) -> int:
        strength = self.pipeline_config.preprocessing.denoise_strength
        if strength >= 0.8:
            return 5
        if strength >= 0.35:
            return 3
        return 1

    def _adjust_exposure(
        self,
        image: Image.Image,
        *,
        brightness_before: float,
        night_mode: bool,
    ) -> tuple[Image.Image, bool]:
        target = self.pipeline_config.preprocessing.target_mean_brightness
        if target <= 0:
            return image, False

        if night_mode:
            ratio = max(target / max(brightness_before, 1.0), 1.0)
            brightness_factor = min(max(ratio, 1.0), 1.6)
            gamma = min(max(1.0 / ratio, 0.7), 1.0)
        else:
            if brightness_before <= target * 1.05:
                return image, False
            brightness_factor = max(target / brightness_before, 0.8)
            gamma = min(max(brightness_before / max(target, 1.0), 1.0), 1.35)

        if abs(brightness_factor - 1.0) < 0.02 and abs(gamma - 1.0) < 0.02:
            return image, False

        adjusted = ImageEnhance.Brightness(image).enhance(brightness_factor)
        adjusted = self._apply_gamma(adjusted, gamma)
        return adjusted, True

    def _denoise(
        self,
        image: Image.Image,
        *,
        backend: PreprocessingBackend,
    ) -> tuple[Image.Image, bool]:
        if backend == PreprocessingBackend.opencv:
            cv2_module = self._cv2()
            if cv2_module is not None:
                denoised = self._denoise_with_opencv(image)
                return denoised, True

        filter_size = self._median_filter_size()
        if filter_size > 1:
            return image.filter(ImageFilter.MedianFilter(size=filter_size)), True
        return image, False

    def _enhance_contrast(
        self,
        image: Image.Image,
        *,
        backend: PreprocessingBackend,
        night_mode: bool,
    ) -> tuple[Image.Image, bool]:
        if backend == PreprocessingBackend.opencv:
            cv2_module = self._cv2()
            if cv2_module is not None:
                return self._enhance_with_opencv(image, night_mode=night_mode), True

        clip_cutoff = min(max(self.pipeline_config.preprocessing.contrast_clip_limit * 1.5, 0.0), 10.0)
        if night_mode:
            grayscale = ImageOps.grayscale(image)
            lifted = ImageEnhance.Brightness(grayscale).enhance(1.15)
            return ImageOps.autocontrast(ImageOps.equalize(lifted), cutoff=clip_cutoff).convert("RGB"), False
        return ImageOps.autocontrast(image, cutoff=clip_cutoff), False

    def _load_image(self, crop_source: str | Path | Image.Image) -> Image.Image:
        if isinstance(crop_source, Image.Image):
            return crop_source.convert("RGB")

        with Image.open(crop_source) as image:
            return image.convert("RGB")

    def _apply_gamma(self, image: Image.Image, gamma: float) -> Image.Image:
        if abs(gamma - 1.0) < 0.01:
            return image

        lut = [min(255, max(0, round(((index / 255.0) ** gamma) * 255.0))) for index in range(256)]
        return image.point(lut * len(image.getbands()))

    def _cv2(self):
        try:
            import cv2  # type: ignore
        except ImportError:
            return None
        return cv2

    def _numpy(self):
        try:
            import numpy as np  # type: ignore
        except ImportError:
            return None
        return np

    def _denoise_with_opencv(self, image: Image.Image) -> Image.Image:
        cv2_module = self._cv2()
        np_module = self._numpy()
        if cv2_module is None or np_module is None:
            return image

        rgb = np_module.array(image)
        bgr = cv2_module.cvtColor(rgb, cv2_module.COLOR_RGB2BGR)
        strength = int(5 + (self.pipeline_config.preprocessing.denoise_strength * 12))
        denoised = cv2_module.fastNlMeansDenoisingColored(bgr, None, strength, strength, 7, 21)
        restored = cv2_module.cvtColor(denoised, cv2_module.COLOR_BGR2RGB)
        return Image.fromarray(restored)

    def _enhance_with_opencv(self, image: Image.Image, *, night_mode: bool) -> Image.Image:
        cv2_module = self._cv2()
        np_module = self._numpy()
        if cv2_module is None or np_module is None:
            return image

        rgb = np_module.array(image)
        lab = cv2_module.cvtColor(rgb, cv2_module.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2_module.split(lab)
        clip_limit = float(max(self.pipeline_config.preprocessing.contrast_clip_limit, 1.0))
        tile_size = int(self.pipeline_config.preprocessing.clahe_tile_grid_size)
        clahe = cv2_module.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
        l_channel = clahe.apply(l_channel)
        if night_mode:
            l_channel = cv2_module.convertScaleAbs(l_channel, alpha=1.08, beta=6.0)
        merged = cv2_module.merge((l_channel, a_channel, b_channel))
        enhanced = cv2_module.cvtColor(merged, cv2_module.COLOR_LAB2RGB)
        return Image.fromarray(enhanced)

    def _rectify_with_opencv(
        self,
        image: Image.Image,
        *,
        corners: Sequence[tuple[float, float]],
        output_size: tuple[int, int],
    ) -> Image.Image:
        cv2_module = self._cv2()
        np_module = self._numpy()
        if cv2_module is None or np_module is None:
            return self._rectify_with_pillow(image, corners=corners, output_size=output_size)

        source = np_module.array(corners, dtype="float32")
        destination = np_module.array(
            [
                [0, 0],
                [output_size[0] - 1, 0],
                [output_size[0] - 1, output_size[1] - 1],
                [0, output_size[1] - 1],
            ],
            dtype="float32",
        )
        matrix = cv2_module.getPerspectiveTransform(source, destination)
        warped = cv2_module.warpPerspective(np_module.array(image), matrix, output_size)
        return Image.fromarray(warped)

    def _rectify_with_pillow(
        self,
        image: Image.Image,
        *,
        corners: Sequence[tuple[float, float]],
        output_size: tuple[int, int],
    ) -> Image.Image:
        quad = (
            corners[0][0],
            corners[0][1],
            corners[1][0],
            corners[1][1],
            corners[2][0],
            corners[2][1],
            corners[3][0],
            corners[3][1],
        )
        return image.transform(output_size, Image.Transform.QUAD, quad, resample=Image.Resampling.BICUBIC)
