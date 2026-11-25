"""Counterfactual checks using different measurements and independent site reports."""
import pytest
from crs import task_decisions as t
from crs.site_updates import site_update
from crs_engine import CRSEngine


@pytest.mark.parametrize("depth,clear,expected", [(4.9, True, t.YES), (5, True, t.UNKNOWN),
                                                   (3, False, t.UNKNOWN)])
def test_shallow_exception_boundary(depth, clear, expected):
    facts = {"depth_ft": depth, "competent_person_no_cave_in": clear}
    assert t.protection(facts.get)[0] == expected


@pytest.mark.parametrize("depth,distance,expected", [(3.9, 26, None), (4, 25, t.YES), (4, 25.1, t.NO)])
def test_route_boundaries(depth, distance, expected):
    facts = {"is_trench": True, "depth_ft": depth, "only_suitable_exit": True,
             "ladder_lateral_distance_ft": distance, "ladder_distance_verified": True,
             "safe_egress_within_25ft": distance <= 25}
    decision = t.egress(facts.get)
    assert (decision[0] if decision else None) == expected


def test_vertical_move_distinct_from_unverified_horizontal_move():
    facts, _ = site_update("The crane is moving the shield vertically. Workers remain inside the shield.", {})
    assert t.movement(facts.get)[0] == t.NO
    facts["shield_install_remove_vertical"] = False
    assert t.movement(facts.get)[0] == t.WAIT


def test_new_route_supersedes_old_verified_route():
    prior = {"safe_egress_within_25ft": True, "task_hazards_verified": True}
    patch, _ = site_update("Workers travel 38 feet laterally to a ladder.", prior)
    assert patch["safe_egress_within_25ft"] is None
    assert patch["task_hazards_verified"] is None


def test_pending_inspection_cannot_be_evidence():
    patch, _ = site_update("If the competent person verifies safe access and all hazards for the defined task, the plan could proceed.", {})
    assert not patch.get("task_hazards_verified")


def test_evidence_survives_unrelated_update(tmp_path):
    db = CRSEngine(tmp_path / "task.db")
    view = db.create({"is_trench": True, "depth_ft": 7.5, "ladder_distance_conflicted": True})
    def route(view):
        return next(f for f in view["task_findings"] if f["decision_id"] == "egress")
    old = route(view)
    new = db.revise(view["scenario_id"], {"water_accumulating": True})
    assert route(new) == old
    assert next(f for f in new["task_findings"] if f["decision_id"] == "water_precautions")["status"] == t.WAIT
    assert old["dependencies"]["ladder_distance_conflicted"]["state_id"]


def test_atomic_assessment_rollback(tmp_path):
    db = CRSEngine(tmp_path / "rollback.db")
    s = db.create({"depth_ft": 3})
    with pytest.raises(RuntimeError):
        with db.atomic():
            db.revise(s["scenario_id"], {"depth_ft": 9}, expected_version=1)
            raise RuntimeError("interrupted audit write")
    assert db.get(s["scenario_id"])["conditions"]["depth_ft"] == 3


def test_quote_matches_the_specific_paragraph():
    from crs.assistant import _paragraph_quotes
    p = {"citation":"1926.651(c)(2)", "text":"no more than 25 feet of lateral travel",
         "id":"p1", "sha256":"digest", "edition":"2025-07-01"}
    item = {"citation":p["citation"], "quote":p["text"], "claim":"Lateral travel limit"}
    assert len(_paragraph_quotes([item], [p], [p["citation"]])) == 1
    assert not _paragraph_quotes([{**item, "quote":"no more than 50 feet of lateral travel"}], [p], [p["citation"]])
