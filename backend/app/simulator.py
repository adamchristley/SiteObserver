"""Deterministic synthetic site telemetry with a bounded incident log."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from math import atan2, cos, sin
from threading import Lock
from time import monotonic

from .models import Actor, Incident, SiteSnapshot, Zone
from .risk import evaluate

ZONES = [
    Zone(id="z-excavation", label="Excavation exclusion zone", x=10, y=5, width=20, height=10),
    Zone(id="z-loading", label="Loading bay", x=55, y=32, width=17, height=14, restricted=False),
]


def moving_actor(
    id: str, kind: str, label: str, x: float, y: float, vx: float, vy: float
) -> Actor:
    return Actor(id=id, kind=kind, label=label, x=round(x, 3), y=round(y, 3),
                 vx=round(vx, 3), vy=round(vy, 3), heading=atan2(vy, vx))


def make_actors(t: float) -> list[Actor]:
    """Synthetic trajectories; position/velocity in meters and meters/second."""
    return [
        moving_actor("w-01", "worker", "Worker 01",
                     18 + 5 * sin(t / 9 + 0.5), 20 + 3 * cos(t / 11),
                     5 / 9 * cos(t / 9 + 0.5), -3 / 11 * sin(t / 11)),
        moving_actor("w-02", "worker", "Worker 02",
                     40 + 6 * sin(t / 12), 13 + 3 * cos(t / 8),
                     0.5 * cos(t / 12), -3 / 8 * sin(t / 8)),
        moving_actor("w-03", "worker", "Worker 03",
                     53 + 6 * sin(t / 7 + 2), 37 + 4 * cos(t / 8 + 2),
                     6 / 7 * cos(t / 7 + 2), -0.5 * sin(t / 8 + 2)),
        moving_actor("w-04", "worker", "Worker 04",
                     16 + 3 * sin(t / 6 + 1), 13 + 5 * cos(t / 8 + 1),
                     0.5 * cos(t / 6 + 1), -5 / 8 * sin(t / 8 + 1)),
        moving_actor("m-01", "excavator", "Excavator 01",
                     17 + 8 * sin(t / 10), 19 + 2 * cos(t / 14),
                     0.8 * cos(t / 10), -2 / 14 * sin(t / 14)),
        moving_actor("m-02", "truck", "Haul Truck 02",
                     58 - 9 * sin(t / 10), 37 + 2 * sin(t / 12),
                     -0.9 * cos(t / 10), 2 / 12 * cos(t / 12)),
    ]


class SiteSimulator:
    """Advances on demand: no billable external services or background workers."""

    def __init__(self, clock=monotonic):
        self._clock = clock
        self._started = clock()
        self._lock = Lock()
        self._incidents: deque[Incident] = deque(maxlen=250)
        self._active: dict[str, str] = {}

    def snapshot(self) -> SiteSnapshot:
        with self._lock:
            elapsed = max(0.0, self._clock() - self._started)
            actors = make_actors(elapsed)
            hazards = evaluate(actors, ZONES)
            current = {h.id: h.severity for h in hazards}
            timestamp = datetime.now(timezone.utc)
            for hazard in hazards:
                if self._active.get(hazard.id) != hazard.severity:
                    self._incidents.appendleft(Incident(**hazard.model_dump(), detected_at=timestamp))
            self._active = current
            return SiteSnapshot(
                timestamp=timestamp, elapsed_s=round(elapsed, 2),
                actors=actors, zones=ZONES, hazards=hazards,
                incidents_total=len(self._incidents),
                people_on_site=sum(a.kind == "worker" for a in actors),
                equipment_active=sum(a.kind != "worker" for a in actors),
            )

    def incidents(self, limit: int = 30) -> list[Incident]:
        with self._lock:
            return list(self._incidents)[:limit]
