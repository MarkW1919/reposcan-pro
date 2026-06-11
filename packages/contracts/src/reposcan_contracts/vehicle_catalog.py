"""Vehicle recognition catalog contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .types import UtcTimestamp


class VehicleCatalogSeedEntry(BaseModel):
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    start_year: int = Field(..., ge=1900, le=2100)
    end_year: int = Field(..., ge=1900, le=2100)
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None
    raw_row: str | None = None

    @computed_field
    @property
    def placeholder(self) -> bool:
        lowered_model = self.model.lower()
        return lowered_model.startswith("(") or "database coverage" in lowered_model


class VehicleCatalogOverrideEntry(BaseModel):
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)
    source_models: list[str] = Field(default_factory=list)
    notes: str | None = None


class VehicleCatalogEntry(BaseModel):
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    requested_start_year: int = Field(..., ge=1900, le=2100)
    requested_end_year: int = Field(..., ge=1900, le=2100)
    available_years: list[int] = Field(default_factory=list)
    matched_source_models: list[str] = Field(default_factory=list)
    status: Literal["matched", "partial", "missing", "placeholder"] = "matched"
    notes: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def first_available_year(self) -> int | None:
        return min(self.available_years) if self.available_years else None

    @computed_field
    @property
    def last_available_year(self) -> int | None:
        return max(self.available_years) if self.available_years else None


class VehicleRecognitionLabel(BaseModel):
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    year: int = Field(..., ge=1900, le=2100)
    label: str = Field(..., min_length=1)


class VehicleRecognitionCatalog(BaseModel):
    catalog_name: str = Field(..., min_length=1)
    region: str = Field("us", min_length=1)
    source: str = Field("nhtsa_vpic", min_length=1)
    generated_at_utc: UtcTimestamp
    entries: list[VehicleCatalogEntry] = Field(default_factory=list)
    labels: list[VehicleRecognitionLabel] = Field(default_factory=list)
