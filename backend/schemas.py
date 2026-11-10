"""Owned restaurant identities, source provenance and independent personal preferences."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
PlaceStatus = Literal["want_to_try", "tried", "avoid"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RestaurantCreate(Contract):
    name: Name
    branch: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] = ""
    address: Address
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    branch_confirmed: Literal[True]
    osm_id: Annotated[str, StringConstraints(pattern=r"^(node|way|relation)/[1-9][0-9]*$")] | None = None


class PersonalInput(Contract):
    favorite: bool = False
    status: PlaceStatus = "want_to_try"
    personal_rating: float | None = Field(default=None, ge=0, le=5)
    notes: str = Field(default="", max_length=4000)
    revision: int = Field(ge=1, le=9_007_199_254_740_991)


class PersonalPlace(PersonalInput):
    updated_at: datetime


class OsmEvidence(Contract):
    osm_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    category: str
    source_url: str
    observed_at: datetime
    license: str


class Source(Contract):
    id: str
    kind: Literal["user_manual"]
    permission_basis: str
    observed_at: datetime
    storage_allowed: bool
    cloud_eligible: bool
    osm_origin: OsmEvidence | None = None


class Restaurant(Contract):
    id: str
    version: int
    name: str
    branch: str
    address: str
    latitude: float
    longitude: float
    created_at: datetime
    source: Source
    personal: PersonalPlace


class RestaurantResult(Contract):
    data: Restaurant


class PageMeta(Contract):
    total: int
    limit: int
    offset: int


class RestaurantPage(Contract):
    data: list[Restaurant]
    meta: PageMeta
