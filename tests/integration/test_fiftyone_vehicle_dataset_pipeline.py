from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_pipeline_module():
    path = REPO_ROOT / "scripts" / "fiftyone_vehicle_dataset_pipeline.py"
    spec = importlib.util.spec_from_file_location("fiftyone_vehicle_dataset_pipeline", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSample:
    def __init__(self) -> None:
        self.fields: dict[str, object] = {}
        self.tags: list[str] = []
        self.saved = False

    def get_field(self, field_name: str):
        return self.fields.get(field_name)

    def __setitem__(self, field_name: str, value) -> None:
        self.fields[field_name] = value

    def save(self) -> None:
        self.saved = True


class _FakeSampleCollection:
    def __init__(self, dataset: "_FakeDataset") -> None:
        self.dataset = dataset

    def count_documents(self, _query) -> int:
        return len(self.dataset.samples)


class _FakeDataset:
    def __init__(self, name: str, sample_count: int) -> None:
        self.name = name
        self.samples = [_FakeSample() for _ in range(sample_count)]
        self.info: dict[str, object] = {}
        self.persistent = False
        self.merge_calls: list[dict[str, object]] = []
        self._sample_collection = _FakeSampleCollection(self)

    def __iter__(self):
        return iter(self.samples)

    def merge_samples(self, other, **kwargs) -> None:
        self.merge_calls.append(kwargs)
        if len(other.samples) > len(self.samples):
            self.samples.extend(_FakeSample() for _ in range(len(other.samples) - len(self.samples)))

    def save(self) -> None:
        pass


class _FakeFiftyOne:
    def __init__(self) -> None:
        self.datasets = {"target": _FakeDataset("target", 2)}
        self.config = argparse.Namespace(dataset_zoo_dir="")

    def dataset_exists(self, dataset_name: str) -> bool:
        return dataset_name in self.datasets

    def load_dataset(self, dataset_name: str):
        return self.datasets[dataset_name]

    def delete_dataset(self, dataset_name: str) -> None:
        self.datasets.pop(dataset_name, None)


class _FakeZoo:
    def __init__(self, fake_fo: _FakeFiftyOne) -> None:
        self.fake_fo = fake_fo

    def load_zoo_dataset(self, *_args, dataset_name: str, max_samples: int, **_kwargs):
        dataset = _FakeDataset(dataset_name, max_samples)
        self.fake_fo.datasets[dataset_name] = dataset
        return dataset


def test_pull_open_images_expands_existing_dataset(monkeypatch):
    module = _load_pipeline_module()
    fake_fo = _FakeFiftyOne()
    fake_zoo = _FakeZoo(fake_fo)
    monkeypatch.setattr(module, "_require_fiftyone", lambda: (fake_fo, fake_zoo))

    result = module.pull_open_images(
        argparse.Namespace(
            dataset_name="target",
            split="validation",
            classes=["Car", "Truck"],
            max_samples=5,
            label_types=["detections"],
            zoo_dir=None,
            non_persistent=False,
            replace_existing=False,
            launch_app=False,
            port=5151,
        )
    )

    dataset = fake_fo.datasets["target"]
    assert result == 0
    assert len(dataset.samples) == 5
    assert dataset.persistent is True
    assert dataset.merge_calls[0]["skip_existing"] is True
    assert all(sample.saved for sample in dataset.samples)
    assert all("reposcan_candidate" in sample.tags for sample in dataset.samples)
    assert not any(name.startswith("target_pull_") for name in fake_fo.datasets)


def test_export_root_requires_overwrite_for_non_empty_directory(tmp_path):
    module = _load_pipeline_module()
    output_root = tmp_path / "export"
    output_root.mkdir()
    (output_root / "stale.txt").write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError):
        module._prepare_export_root(output_root, overwrite=False)

    module._prepare_export_root(output_root, overwrite=True)

    assert output_root.is_dir()
    assert not (output_root / "stale.txt").exists()
