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
    proj_transform: list[float] | None = Field(None, alias="proj:transform")
    proj_shape: list[int] | None = Field(None, alias="proj:shape")
    s1_shape: list[int] | None = Field(None, alias="s1:shape")
    gsd: float | None = None
    sun_elevation: float | None = Field(None, alias="view:sun_elevation")
    sun_azimuth: float | None = Field(None, alias="view:sun_azimuth")
    view_off_nadir: float | None = Field(None, alias="view:off_nadir")


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
        # Infer EPSG:4326 when we can compute transform from bbox + shape
        # (STAC item bbox is always WGS84 per spec)
        shape = self.properties.proj_shape or self.properties.s1_shape
        if shape and len(shape) >= 2 and self.bbox and len(self.bbox) >= 4:
            return "EPSG:4326"
        return None

    @property
    def proj_affine(self) -> list[float] | None:
        """Return proj:transform as a 6-element affine list, or None."""
        t = self.properties.proj_transform
        if t and len(t) >= 6:
            return t[:6]
        # Compute from bbox + shape (STAC bbox is always EPSG:4326)
        shape = self.properties.proj_shape or self.properties.s1_shape
        if shape and len(shape) >= 2 and self.bbox and len(self.bbox) >= 4:
            height, width = shape[0], shape[1]
            west, south, east, north = self.bbox[:4]
            pixel_x = (east - west) / width
            pixel_y = -(north - south) / height
            return [pixel_x, 0.0, west, 0.0, pixel_y, north]
        return None
