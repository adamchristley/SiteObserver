"""Typed contracts shared by the simulator, risk engine and API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "warning"]


class Actor(BaseModel):
    id: str
    kind: Literal["worker", "excavator", "truck", "forklift"]
    label: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    heading: float = 0.0


class Zone(BaseModel):
    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    restricted: bool = True


class Hazard(BaseModel):
    id: str
    severity: Severity
    category: Literal["proximity", "projected_collision", "restricted_zone"]
    description: str
    actor_ids: list[str]
    distance_m: float | None = None
    time_to_closest_s: float | None = None
    minimum_separation_m: float | None = None


class Incident(Hazard):
    detected_at: datetime


class SiteSnapshot(BaseModel):
    site_id: str = "research-site-01"
    name: str = "North Excavation Site"
    timestamp: datetime
    elapsed_s: float
    width_m: float = 80
    height_m: float = 50
    mode: Literal["simulation"] = "simulation"
    actors: list[Actor]
    zones: list[Zone]
    hazards: list[Hazard]
    incidents_total: int = Field(ge=0)
    people_on_site: int = Field(ge=0)
    equipment_active: int = Field(ge=0)
