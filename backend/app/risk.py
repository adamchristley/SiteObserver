"""Explainable geometric risk baseline, NOT a trained accident predictor."""
from __future__ import annotations

from math import hypot

from .models import Actor, Hazard, Zone

CRITICAL_DISTANCE_M = 2.5
WARNING_DISTANCE_M = 5.0
PREDICTION_HORIZON_S = 4.0


def closest_approach(worker: Actor, machine: Actor, horizon_s: float = PREDICTION_HORIZON_S) -> tuple[float, float]:
    """Return (seconds until closest approach, meters of separation) for constant velocity.

    Positions must be calibrated in *meters*. This is not appropriate for raw
    camera pixels without geometry calibration.
    """
    if horizon_s < 0:
        raise ValueError("horizon_s must be nonnegative")
    dx, dy = machine.x - worker.x, machine.y - worker.y
    dvx, dvy = machine.vx - worker.vx, machine.vy - worker.vy
    speed_squared = dvx * dvx + dvy * dvy
    if speed_squared < 1e-12:
        return 0.0, hypot(dx, dy)
    t = max(0.0, min(horizon_s, -(dx * dvx + dy * dvy) / speed_squared))
    return t, hypot(dx + dvx * t, dy + dvy * t)


def evaluate(actors: list[Actor], zones: list[Zone]) -> list[Hazard]:
    """Detect near misses and restricted-zone entries with stable event IDs."""
    workers = [a for a in actors if a.kind == "worker"]
    machines = [a for a in actors if a.kind != "worker"]
    hazards: list[Hazard] = []

    for worker in workers:
        for machine in machines:
            distance = hypot(machine.x - worker.x, machine.y - worker.y)
            t, predicted_distance = closest_approach(worker, machine)
            if distance <= CRITICAL_DISTANCE_M:
                severity = "critical"
                category = "proximity"
            elif t > 0 and predicted_distance <= CRITICAL_DISTANCE_M:
                severity = "critical"
                category = "projected_collision"
            elif distance <= WARNING_DISTANCE_M:
                severity = "warning"
                category = "proximity"
            elif t > 0 and predicted_distance <= WARNING_DISTANCE_M:
                severity = "warning"
                category = "projected_collision"
            else:
                continue
            explanation = (
                f"{worker.label} is {distance:.1f} m from {machine.label}"
                if category == "proximity"
                else f"{worker.label} and {machine.label} may approach within {predicted_distance:.1f} m in {t:.1f} s"
            )
            hazards.append(
                Hazard(
                    id=f"equipment:{worker.id}:{machine.id}",
                    severity=severity,
                    category=category,
                    description=explanation,
                    actor_ids=[worker.id, machine.id],
                    distance_m=round(distance, 2),
                    time_to_closest_s=round(t, 2),
                    minimum_separation_m=round(predicted_distance, 2),
                )
            )

        for zone in zones:
            if not zone.restricted:
                continue
            if zone.x <= worker.x <= zone.x + zone.width and zone.y <= worker.y <= zone.y + zone.height:
                hazards.append(
                    Hazard(
                        id=f"zone:{worker.id}:{zone.id}",
                        severity="critical",
                        category="restricted_zone",
                        description=f"{worker.label} entered {zone.label}",
                        actor_ids=[worker.id],
                    )
                )

    return sorted(hazards, key=lambda h: (h.severity != "critical", h.id))
