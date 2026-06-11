"""Media layout helpers for the storage service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaLayout:
    root: Path
    frames: Path
    crops: Path
    snippets: Path
    exports: Path


def ensure_media_layout(root: str | Path) -> MediaLayout:
    base = Path(root)
    frames = base / "frames"
    crops = base / "crops"
    snippets = base / "snippets"
    exports = base / "exports"

    for path in (base, frames, crops, snippets, exports):
        path.mkdir(parents=True, exist_ok=True)

    return MediaLayout(
        root=base,
        frames=frames,
        crops=crops,
        snippets=snippets,
        exports=exports,
    )
