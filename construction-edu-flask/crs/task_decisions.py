"""Scoped excavation decisions. A dependency is a fact read by a particular check."""
import json

YES = "Approved"
NO = "Not Approved"
WAIT = "Pending Verification"
UNKNOWN = "Insufficient Information"
CRITERIA = {
    YES: "Evidence supports every applicable check for the defined task and conditions.",
    NO: "A reported condition or proposed operation fails an applicable requirement.",
    WAIT: "An identified claim, correction, conflict or planned control needs verification.",
    UNKNOWN: "An essential site fact is missing and no more specific finding is supported.",
}
PROTECT = "1926.652(a)(1)"
SHALLOW = "1926.652(a)(1)(ii)"
CAPACITY = "1926.652(a)(2)"
INSPECT = "1926.651(k)(1)"
REMOVE = "1926.651(k)(2)"
EGRESS = "1926.651(c)(2)"
LOAD = "1926.652(g)(1)(i)"
ACCESS = "1926.652(g)(1)(iii)"
MOVEMENT = "1926.652(g)(1)(iv)"


def protection(get):
    depth = get("depth_ft")
    soil = get("soil_type")
    if get("stable_rock") is True:
        return YES, "The stable-rock exception applies to the stated excavation.", ["1926.652(a)(1)(i)"]
    if depth is None:
        return UNKNOWN, "Establish depth and ground conditions.", [PROTECT]
    if depth < 5:
        if get("competent_person_cave_in_indication") and get("protective_system") != "verified":
            return NO, "The instability finding invalidates the shallow exception. Establish adequate protection.", [PROTECT, SHALLOW]
        if get("competent_person_no_cave_in") and not get("competent_person_cave_in_indication"):
            return YES, "The competent-person finding supports the under-five-foot exception.", [SHALLOW]
        if get("inspection_before_work") is False:
            return NO, "The proposed shallow exception lacks the required examination.", [PROTECT, SHALLOW]
    if get("protective_system") == "none" and (get("stable_rock") is False or get("soil_type") in ("A","B","C")):
        return NO, "Provide adequate cave-in protection before exposure.", [PROTECT]
    if get("protective_system") == "verified":
        return YES, "The reported design covers the assessed loads.", [PROTECT, CAPACITY]
    duty = (f"The reported {depth:g}-foot excavation in Type {soil} soil requires cave-in protection. "
            if depth >= 5 and soil in ("A", "B", "C") else "")
    return (WAIT if get("shield_removed") or get("protection_awaits_verification") else UNKNOWN,
            duty + "Establish the applicable design and capacity for the current configuration.", [PROTECT, CAPACITY])


def coverage(get):
    if not (get("shield_count") or get("shield_removed") or get("worker_outside_shield") or get("protection_awaits_verification")):
        return None
    removed = get("shield_removed")
    if get("worker_outside_shield") and not get("shield_coverage_verified"):
        return NO, "Keep workers out of the unsupported position until protection covers it.", [PROTECT, ACCESS]
    checks = [get(k) for k in ("shield_configuration_verified", "shield_capacity_verified", "shield_coverage_verified")]
    if all(checks):
        return YES, "The reported checks cover configuration, capacity and worker positions.", [CAPACITY, LOAD, ACCESS]
    return (WAIT if removed or get("protection_awaits_verification") else UNKNOWN,
            "Verify rated capacity, occupied positions and protected entry and exit.", [CAPACITY, LOAD, ACCESS])


def egress(get):
    if get("is_trench") is not True:
        return None
    depth = get("depth_ft")
    if depth is None:
        return UNKNOWN, "Establish whether the trench reaches four feet.", [EGRESS]
    if depth < 4:
        return None
    if get("ladder_distance_conflicted"):
        reports = get("obs_disputed_routes_ft")
        alternatives = []
        for value in (reports or "").split(", "):
            if value.replace(".", "", 1).isdigit():
                judgment = "within" if float(value) <= 25 else "over"
                alternatives.append(f"{value} feet would be {judgment} the 25-foot limit")
        return WAIT, "Measure lateral travel from all assigned positions. " + ". ".join(alternatives), [EGRESS]
    distance = get("ladder_lateral_distance_ft")
    access = get("safe_egress_within_25ft")
    only_exit = get("only_suitable_exit")
    if access is False or (only_exit and distance is not None and distance > 25):
        return NO, "Provide suitable egress within 25 feet of lateral travel.", [EGRESS]
    if access is True and get("ladder_distance_verified"):
        return YES, "The reported verified route meets the 25-foot lateral travel limit.", [EGRESS]
    return (WAIT if distance is not None or get("ladder_reported") else UNKNOWN,
            "Verify suitable egress within 25 feet from each occupied position.", [EGRESS])


def inspection(get):
    instability = get("competent_person_cave_in_indication")
    if instability:
        return NO, "Remove exposed employees until adequate precautions address the instability.", [REMOVE]
    if get("shield_removed") or get("shield_moving") or get("rain_event"):
        if not get("inspection_after_change"):
            return WAIT, "Verify competent-person inspection after the hazard-increasing change.", [INSPECT]
    inspected = get("inspection_before_work")
    if inspected is False:
        return NO, "Complete the competent-person inspection before entry.", [INSPECT]
    if inspected:
        return YES, "The pre-work inspection is reported complete. If evidence of a cave-in develops, remove exposed employees until precautions are in place.", [INSPECT, REMOVE]
    return UNKNOWN, "Obtain the competent-person pre-work inspection finding.", [INSPECT]


def movement(get):
    if not get("shield_moving"):
        return None
    if get("evacuation_planned"):
        return WAIT, "Confirm actual clearance before movement and installation at the destination before reentry.", [MOVEMENT, "1926.652(g)(1)(ii)", ACCESS]
    if get("shield_install_remove_vertical") and get("workers_inside_moving_shield"):
        return NO, "Clear the shield before installation, removal or vertical movement.", [MOVEMENT]
    if get("workers_in_trench_during_shield_movement") and get("worker_outside_shield"):
        return NO, "The proposed move leaves the identified exposure unresolved. Maintain protection throughout movement, verify loads and installation, and keep workers clear of suspended loads if lifting equipment is used.", [PROTECT, LOAD, "1926.652(g)(1)(ii)", ACCESS, MOVEMENT, "1926.651(e)"]
    return WAIT, "Verify continuous protection. Workers may not occupy shields during installation, removal or vertical movement.", [MOVEMENT, PROTECT]


def extension(get):
    depth = get("planned_depth_ft")
    if depth is None and not get("extension_planned"):
        return None
    ground = get("extension_soil_verified")
    note = "Soil in the proposed area awaits verification. " if not ground else ""
    return WAIT, note + "Determine design loads and coverage for the new ground and geometry. Evaluate applicable sloping or shield design options.", [PROTECT, CAPACITY, "1926.652(b)(1)(i)", "1926.652(b)(1)(ii)", "1926.652(c)(2)(i)", "1926.652(c)(4)(i)"]


def extension_access(get):
    depth = get("planned_depth_ft")
    expanded = get("extension_planned")
    if depth is None and not expanded:
        return None
    if depth is not None and depth < 4:
        return None
    return WAIT, "Verify the route from every new work position before extending the task. The earlier route measurement covers only the existing area.", [EGRESS]


def readiness(get):
    if get("obs_other_hazard_reported"):
        return WAIT, "Assess the additional reported hazard before extending the defined task finding.", [INSPECT]
    if get("task_hazards_verified"):
        return YES, "The competent person verified the applicable hazards for the defined task.", [INSPECT]
    return UNKNOWN, "Define the work limits and verify applicable site hazards.", [INSPECT]


def water(get):
    if not get("water_accumulating"):
        return None
    precautions = get("water_precautions_adequate")
    if precautions is True:
        return YES, "Adequate precautions against accumulating water are reported.", ["1926.651(h)(1)"]
    return (NO if precautions is False else WAIT,
            "Verify adequate water precautions before exposing workers.", ["1926.651(h)(1)"])


def spoils(get):
    if not get("spoil_hazard"):
        return None
    distance = get("spoil_distance_ft")
    retained = get("spoil_retained")
    if retained or (distance is not None and distance >= 2):
        return YES, "The reported setback or retaining device addresses the falling-material hazard.", ["1926.651(j)(2)"]
    return (NO if distance is not None and retained is False else WAIT,
            "Provide adequate setback or retention for material that could enter the excavation.", ["1926.651(j)(2)"])


def utilities(get):
    if not get("utilities_expected"):
        return None
    if get("utility_locations_estimated"):
        return YES, "Estimated utility locations were determined for this check.", ["1926.651(b)(1)"]
    return (NO if get("excavation_opened") and get("utility_locations_estimated") is False else WAIT,
            "Determine expected utility locations before opening the excavation.", ["1926.651(b)(1)"])


CHECKS = {"protection": protection, "worker_coverage": coverage, "egress": egress,
          "inspection": inspection, "shield_movement": movement, "extension_design": extension, "extension_egress": extension_access,
          "task_scope": readiness, "water_precautions": water, "spoil_controls": spoils,
          "utility_locations": utilities}


def evaluate_check(check, state):
    reads = {}
    def read(key):
        reads[key] = state.get(key)
        return reads[key]
    read("work_area")
    active = read("is_trench") or read("depth_ft") is not None
    finding = check(read) if active else None
    return reads, finding


def update(db, sid, branch, version, state, changes):
    previous = {r["name"]: json.loads(r["body"]) for r in db.execute(
        "SELECT name,body FROM task_findings WHERE scenario_id=? AND branch=?", (sid, branch))}
    facts = {r["key"]: r["state_id"] for r in db.execute(
        "SELECT key,state_id FROM state_facts WHERE scenario_id=? AND branch=? AND status='active'", (sid, branch))}
    for name, check in CHECKS.items():
        old = previous.get(name)
        triggers = sorted(set(changes) & set(old["dependencies"])) if old else []
        if old and not triggers:
            continue
        reads, finding = evaluate_check(check, state)
        body = {"decision_id": name, "status": finding[0] if finding else None,
                "reason": finding[1] if finding else "", "citations": finding[2] if finding else [],
                "dependencies": {k: {"value": v, "state_id": facts.get(k)} for k, v in reads.items()},
                "evaluated_version": version, "triggers": triggers,
                "previous_status": old["status"] if old else None}
        db.execute("INSERT INTO task_findings VALUES (?,?,?,?) ON CONFLICT(scenario_id,branch,name) "
                   "DO UPDATE SET body=excluded.body", (sid, branch, name, json.dumps(body)))


def classify(items, state, legacy):
    statuses = {i["status"] for i in items}
    if NO in statuses or any(i["status"] == "noncompliant" for i in legacy):
        return NO
    if WAIT in statuses:
        return WAIT
    if statuses == {YES} and state.get("task_hazards_verified") and not any(k.startswith("obs_") for k in state):
        return YES
    return UNKNOWN
