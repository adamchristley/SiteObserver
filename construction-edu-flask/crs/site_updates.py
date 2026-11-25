"""Normalize reported excavation changes before classifying the scoped task."""
import re
from .extractor import extract_conditions
from crs_engine import CRSInputError


def site_update(text, prior):
    # Question clauses are requests, not observed field conditions.
    statements = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if not s.rstrip().endswith("?")]
    report = " ".join(statements).lower()
    # A conditional prerequisite or future inspection is not evidence of completion.
    affirmative = " ".join(s.lower() for s in statements if not re.search(
        r"\b(?:if|unless|would|might|could|should|must verify|will (?:verify|inspect|measure))\b", s, re.I))
    try:
        facts = extract_conditions(report)["conditions"] if report else {}
    except CRSInputError:
        facts = {}
    def has(pattern):
        return bool(re.search(pattern, report))
    separate = has(r"\b(?:a separate|a new|a different)\b[^.!?]{0,105}\b(?:trench|excavation|section)\b")
    if has(r"\btrench\b|\bexcavation\b.{0,70}\btrench shields?\b"):
        facts.setdefault("is_trench", True)
    soil = re.search(r"\btype ([abc]) (?:soil|trench|excavation)", report)
    if soil:
        facts["soil_type"] = soil[1].upper()
        facts["stable_rock"] = False
    for field, dimension in (("excavation_length_ft", "long"), ("excavation_width_ft", "wide")):
        measure = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?(?:foot|feet|ft)[- ]+" + dimension, report)
        if measure:
            facts[field] = float(measure[1])
    count = re.search(r"\b(one|two|three|\d+) (?:trench )?shields?\b", report)
    if count:
        facts["shield_count"] = {"one":1, "two":2, "three":3}.get(count[1], None)
        if facts["shield_count"] is None:
            facts["shield_count"] = int(count[1])
    if has(r"(?:shield|shielding) (?:has been |was |is |remains )removed") and not has(r"no (?:upper |lower )?shield (?:was |is |has been )removed"):
        facts["shield_removed"] = True
        if not prior.get("shield_removed") and prior.get("shield_count"):
            facts["shield_count"] = max(0, prior["shield_count"] - 1)
        if not prior.get("shield_removed"):
            for key in ("shield_capacity_verified","shield_coverage_verified","shield_configuration_verified","inspection_after_change"):
                facts[key] = None
    if has(r"(?:worker|employee).{0,45}(?:stands?|works?|working) (?:above|outside|beyond).{0,80}(?:unsupported|unprotected)"):
        facts["worker_outside_shield"] = True
        facts["employees_exposed"] = True
        facts["shield_coverage_verified"] = None
    if has(r"(?:mov(?:e|ing)|relocat(?:e|ing)).{0,40}shield|shield (?:is moved|movement)"):
        facts["shield_moving"] = True
        if has(r"while (?:the )?(?:workers|employees) (?:continue|remain|work)"):
            facts["workers_in_trench_during_shield_movement"] = True
            facts["evacuation_planned"] = False
        if has(r"(?:all workers|all employees|everyone) will (?:exit|leave|evacuate) before"):
            facts.update(evacuation_planned=True, workers_in_trench_during_shield_movement=False)
    if has(r"competent person has not (?:yet )?(?:examined|inspected)"):
        facts.update(inspection_before_work=False, competent_person_no_cave_in=None)
    if has(r"competent person (?:completes|completed|performed) (?:the |a )?pre[- ]work (?:examination|inspection)"):
        facts["inspection_before_work"] = True
    if facts.get("inspection_before_work") and has(r"finds? no (?:sign|indication)s? of (?:a |any )?(?:potential )?cave-in"):
        facts.update(competent_person_no_cave_in=True, competent_person_cave_in_indication=False)
    if has(r"competent person.{0,95}(?:noticing|finds?|identifies|observes) (?:signs of )?(?:possible )?(?:instability|cave-in)"):
        facts.update(competent_person_no_cave_in=False, competent_person_cave_in_indication=True,
                     task_hazards_verified=None)
    if (has(r"competent[- ]person (?:has )?(?:verifie[ds]|confirmed|checked)\b") and
            has(r"\b(?:applicable|all) (?:site |task )?hazards\b") and
            has(r"\b(?:defined|specified|scoped|limited) (?:work|task|activity)\b") and
            not has(r"\b(?:unverified|except|unresolved|disputes?|unconfirmed)\b")):
        if re.search(r"competent[- ]person (?:has )?(?:verifie[ds]|confirmed|checked)\b", affirmative):
            facts["task_hazards_verified"] = True
    if has(r"(?:protective arrangement|protection) has not been verified"):
        facts["protection_awaits_verification"] = True
    if has(r"ladder is available"):
        facts["ladder_reported"] = True
    distance = re.search(r"(?:within |travel )(\d+(?:\.\d+)?)\s*(?:feet|ft)\s+laterall?y?\b", report)
    if has(r"disputes?|conflicting|disagree") and has("ladder|distance") and len(re.findall(r"\d+ (?:feet|ft)", report)) >= 2:
        routes = re.findall(r"(\d+(?:\.\d+)?)\s+(?:feet|ft)\b", report)
        facts["obs_disputed_routes_ft"] = ", ".join(dict.fromkeys(routes))
        facts.update(ladder_distance_conflicted=True, ladder_lateral_distance_ft=None,
                     ladder_distance_verified=None, safe_egress_within_25ft=None)
    elif distance and has("ladder|ramp|egress|stairway"):
        ft = float(distance[1])
        only = has(r"only suitable (?:ladder|ramp|exit|stairway)")
        verified = (has(r"(?:measurement confirms|competent person verifies safe access)") and
                    has(r"suitable (?:secured )?(?:ladder|ramp|stairway)") and
                    has(r"every (?:worker|assigned position)|all (?:workers|assigned positions)"))
        facts.update(ladder_lateral_distance_ft=ft, only_suitable_exit=only,
                     ladder_distance_verified=verified, ladder_reported=True)
        facts["safe_egress_within_25ft"] = None
        if verified or only:
            facts["safe_egress_within_25ft"] = ft <= 25 if verified else (False if ft > 25 else None)
        if verified:
            facts["ladder_distance_conflicted"] = False
            facts["obs_disputed_routes_ft"] = None
        elif prior.get("ladder_distance_conflicted"):
            facts.update(ladder_lateral_distance_ft=None, safe_egress_within_25ft=None)
    deeper = re.search(r"(?:propos\w+|plan\w+) (?:to )?deepen\w*.{0,65}?to (\d+(?:\.\d+)?) (?:feet|ft)", report)
    if has(r"(?:propos\w+|plan\w+).{0,100}extend(?:ing)? (?:the )?(?:work area|trench|excavation)"):
        facts["extension_planned"] = True
    if has(r"soil classification for the (?:new|proposed) section has not been confirmed"):
        facts["extension_soil_verified"] = False
    if deeper:
        facts.pop("depth_ft", None)
        facts["planned_depth_ft"] = float(deeper[1])
    if re.search(r"\b(?:vertically mov\w*|mov\w* (?:the )?shield vertically|installing (?:the )?shield|removing (?:the )?shield)\b", report):
        facts["shield_moving"] = True
        facts["shield_install_remove_vertical"] = True
    if re.search(r"\b(?:employees|workers) (?:are |remain |will remain )(?:inside|in) (?:the )?shield\b", report):
        facts["workers_inside_moving_shield"] = True
    if not separate and "depth_ft" in facts and prior.get("depth_ft") not in (None, facts["depth_ft"]):
        for key in ("competent_person_no_cave_in", "inspection_before_work", "shield_capacity_verified",
                    "shield_configuration_verified", "task_hazards_verified"):
            facts.setdefault(key, None)
    if (prior.get("task_hazards_verified") and not facts.get("task_hazards_verified")
            and report and (any(prior.get(k) != v for k, v in facts.items()) or not facts)):
        facts["task_hazards_verified"] = None
    if has(r"\b(?:oxygen[- ]deficien\w*|energized conductor|toxic gas|cracked shield|damaged ladder)\b"):
        facts["obs_other_hazard_reported"] = True
    return facts, separate
