"""Shared metadata contract for exported classifier artifacts."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator

from .dataset import DatasetTask

_YEAR_PATTERN = re.compile(r"^\d{4}(?:-\d{4})?$")


class ClassifierExportLabelRecord(BaseModel):
    index: int = Field(..., ge=0)
    label: str = Field(..., min_length=1)
    color: str | None = None
    make: str | None = None
    model_label: str | None = Field(None, alias="model")
    year: str | None = None

    model_config = {"populate_by_name": True}


class ClassifierExportMetadata(BaseModel):
    metadata_version: int = Field(1, ge=1)
    task: str | None = None
    image_size: int | None = Field(None, gt=0)
    base_model: str | None = None
    classes: list[str] = Field(default_factory=list)
    class_records: list[ClassifierExportLabelRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_classes_from_records(self) -> "ClassifierExportMetadata":
        if not self.classes and self.class_records:
            self.classes = [record.label for record in self.class_records]
        if self.classes and not self.class_records:
            self.class_records = [
                ClassifierExportLabelRecord(index=index, label=label)
                for index, label in enumerate(self.classes)
            ]
        return self

    def record_for_index(self, index: int) -> ClassifierExportLabelRecord | None:
        if 0 <= index < len(self.class_records):
            return self.class_records[index]
        return None


def parse_vehicle_make_model_year(label: str) -> tuple[str | None, str | None, str | None]:
    """Split a class label into (make, model, year).

    Handles both label conventions used in this project:
      * Canonical slugs joined by underscores, e.g. ``chevrolet_suburban``,
        ``ford_f_series``, ``jeep_grand_cherokee`` -> make is the first
        segment, model is the remainder ("suburban", "f series",
        "grand cherokee").
      * Space-separated labels (e.g. Stanford-Cars style
        "Toyota Camry Sedan 2019") -> first token is make, trailing 4-digit
        token is the year, the rest is the model.

    Without the underscore handling, every canonical make/model class
    (which never contains spaces) collapsed into a single token, leaving
    ``model`` null and stuffing the full ``make_model`` slug into ``make``.
    """
    raw = label.strip()
    if not raw:
        return None, None, None

    # Slug form: no spaces but underscore-joined -> split on underscores.
    if " " not in raw and "_" in raw:
        tokens = [token for token in raw.split("_") if token]
    else:
        tokens = [token.strip() for token in raw.split() if token.strip()]
    if not tokens:
        return None, None, None

    year: str | None = None
    if _YEAR_PATTERN.match(tokens[-1]):
        year = tokens.pop()

    if not tokens:
        return None, None, year

    make = tokens[0].lower()
    model_label = " ".join(token.lower() for token in tokens[1:]) or None
    return make, model_label, year


def build_classifier_export_metadata(
    *,
    task: DatasetTask | str,
    classes: list[str],
    image_size: int | None = None,
    base_model: str | None = None,
) -> ClassifierExportMetadata:
    task_value = task.value if isinstance(task, DatasetTask) else str(task)
    class_records: list[ClassifierExportLabelRecord] = []

    for index, label in enumerate(classes):
        normalized_label = label.strip()
        record = ClassifierExportLabelRecord(index=index, label=normalized_label)
        if task_value == DatasetTask.vehicle_color_classification.value:
            record.color = normalized_label.lower()
        elif task_value == DatasetTask.vehicle_make_model_classification.value:
            make, model_label, year = parse_vehicle_make_model_year(normalized_label)
            record.make = make
            record.model_label = model_label
            record.year = year
        elif task_value == DatasetTask.vehicle_year_classification.value:
            record.year = normalized_label
        class_records.append(record)

    return ClassifierExportMetadata(
        task=task_value,
        image_size=image_size,
        base_model=base_model,
        classes=list(classes),
        class_records=class_records,
    )
