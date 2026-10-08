from math import isclose

import pytest

from app.models import Actor, Zone
from app.risk import closest_approach, evaluate


def actor(id, kind, x, y, vx=0, vy=0):
    return Actor(id=id, kind=kind, label=id, x=x, y=y, vx=vx, vy=vy)


def test_approaching_pair_predicts_close_pass():
    person = actor("w", "worker", 0, 0)
    truck = actor("t", "truck", 10, 0, -2, 0)
    t, distance = closest_approach(person, truck)
    assert isclose(t, 4.0)
    assert distance == 2
    hazard = evaluate([person, truck], [])
    assert len(hazard) == 1
    assert hazard[0].category == "projected_collision"
    assert hazard[0].severity == "critical"


def test_receding_pair_is_not_predicted_to_collide():
    person = actor("w", "worker", 0, 0)
    truck = actor("t", "truck", 10, 0, 2, 0)
    assert evaluate([person, truck], []) == []


def test_stationary_nearby_pair_triggers_proximity():
    person = actor("w", "worker", 0, 0)
    machine = actor("e", "excavator", 3, 0)
    hazards = evaluate([person, machine], [])
    assert hazards[0].severity == "warning"
    assert hazards[0].category == "proximity"


def test_exclusion_zone_checks_boundaries():
    person = actor("w", "worker", 10, 10)
    zone = Zone(id="z", label="No entry", x=10, y=10, width=5, height=5)
    hazards = evaluate([person], [zone])
    assert len(hazards) == 1
    assert hazards[0].category == "restricted_zone"


def test_closest_approach_rejects_negative_horizon():
    with pytest.raises(ValueError):
        closest_approach(actor("w", "worker", 0, 0),
                         actor("t", "truck", 2, 0), -1)
