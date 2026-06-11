from __future__ import annotations

import argparse
from pathlib import Path


DATASET_DIRS = ("raw", "staged", "curated", "eval", "manifests")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the local RepoScan Pro dataset workspace layout.")
    parser.add_argument("--root", default="data")
    return parser.parse_args()


def build_workspace(root: Path) -> list[Path]:
    created: list[Path] = []
    root.mkdir(parents=True, exist_ok=True)
    for name in DATASET_DIRS:
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)

    readme = root / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Local Dataset Workspace",
                "",
                "This directory is intentionally machine-local and ignored by git.",
                "",
                "Expected folders:",
                "- `raw` for untouched drops",
                "- `staged` for reviewed intake batches",
                "- `curated` for training-ready datasets",
                "- `eval` for dedicated holdouts and field-eval sets",
                "- `manifests` for intake, split, and registry YAML files",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(readme)
    return created


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    created = build_workspace(root)
    print(f"Dataset workspace: {root}")
    for path in created:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
