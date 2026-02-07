"""
Pydantic models for STAC data structures.

These models replace raw dict[str, Any] usage throughout the codebase,
providing type safety and validated attribute access for STAC items,
assets, and properties.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class STACAsset(BaseModel):
    """A single asset within a STAC item (band, thumbnail, metadata, etc.)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    href: str = ""
    media_type: str | None = Field(None, alias="type")
    gsd: float | None = None
    eo_bands: list[dict[str, Any]] | None = Field(None, alias="eo:bands")


class STACProperties(BaseModel):
    """Properties block of a STAC item."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    datetime: str = ""
    cloud_cover: float | None = Field(None, alias="eo:cloud_cover")
    proj_epsg: int | None = Field(None, alias="proj:epsg")
    proj_code: str | None = Field(None, alias="proj:code")
    gsd: float | None = None


class STACItem(BaseModel):
    """
    A STAC item (scene) with typed access to common fields.

    Uses ``extra="allow"`` so that additional STAC fields are preserved
    when round-tripping through ``model_validate`` / ``model_dump``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    collection: str = ""
    bbox: list[float] = Field(default_factory=list)
    properties: STACProperties = Field(default_factory=STACProperties)
    assets: dict[str, STACAsset] = Field(default_factory=dict)

    @property
    def crs_string(self) -> str | None:
        """Format CRS from properties into 'EPSG:XXXX' form."""
        raw = self.properties.proj_epsg
        if raw is not None:
            return f"EPSG:{raw}"
        code = self.properties.proj_code
        if code is not None:
            return code
        return None
