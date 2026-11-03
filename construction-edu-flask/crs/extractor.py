"""Conservative excavation fact extraction without a paid LLM.

Only explicitly expressed, recognizable claims become CRS facts. Missing facts
are left unknown. This is a narrow research parser, not an OSHA decision maker.
"""
from __future__ import annotations

import re
from crs_engine import CRSInputError, validate_changes

# Longer alternatives first where overlapping terms occur.
UNIT = r'(?:feet|foot|ft\.?|inches|inch|in\.)'
NUM = r'(?P<number>\d+(?:\.\d+)?)'
_DEPTH_PATTERNS = [
    re.compile(rf'\b{NUM}\s*[- ]?\s*(?P<unit>{UNIT})\s*[- ]?\s*(?:deep\b|in\s+depth\b|trench\b|excavation\b|ditch\b)', re.I),
    re.compile(rf'\b(?:trench|excavation|ditch|depth)\b\s*(?:(?:is|was|now|only|about|approximately|around|at|of|to|has|a|changed|decreased|increased|measures|the|depth)\s+){{0,6}}{NUM}\s*[- ]?\s*(?P<unit>{UNIT})\b', re.I),
]
_SPOIL_PATTERNS = [
    re.compile(rf'\b(?:spoil\s*(?:pile|piles|material|materials)?|excavated\s+material(?:s)?)\b.{{0,75}}?\b{NUM}\s*(?P<unit>{UNIT})\s*(?:away\s*)?(?:from|of|off)\s*(?:the\s*)?(?:edge|trench|excavation)', re.I),
    re.compile(rf'\b{NUM}\s*(?P<unit>{UNIT})\s*(?:away\s*)?from\s*(?:the\s*)?(?:edge|trench|excavation)\b.{{0,50}}?\b(?:spoil\b|excavated\s+material)', re.I),
]


def _feet(match):
    value = float(match.group('number'))
    if match.group('unit').lower().startswith('in'):
        value /= 12
    return value


def _has(pattern, text):
    return re.search(pattern, text, re.I) is not None


def extract_conditions(text):
    """Return explicit field/value pairs and matched text; never infer missing facts.

    Raises CRSInputError on empty input, incompatible explicit claims in one
    message, or values the underlying state model cannot represent.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise CRSInputError('text must contain 1 to 2,000 characters')
    text = text.strip()
    conditions, evidence = {}, {}

    def add(key, value, source):
        if key in conditions and conditions[key] != value:
            raise CRSInputError(f'Conflicting statements about {key}; clarify the intended value')
        conditions[key] = value
        evidence.setdefault(key, [])
        snippet = source.strip()
        if snippet not in evidence[key]:
            evidence[key].append(snippet)

    for pattern in _DEPTH_PATTERNS:
        for match in pattern.finditer(text):
            add('depth_ft', _feet(match), match.group())

    for pattern in _SPOIL_PATTERNS:
        for match in pattern.finditer(text):
            add('spoil_distance_ft', _feet(match), match.group())

    # Explicit references to the excavation type, not assumptions about width.
    if _has(r'\b(?:not\s+(?:a\s+)?trench|isn.t\s+(?:a\s+)?trench)\b', text):
        add('is_trench', False, 'not a trench')
    elif _has(r'\btrench(?:es)?\b', text):
        add('is_trench', True, 'trench')

    # Exposure requires workers in the excavation, not merely on the site.
    no_workers = r'\b(?:no|zero)\s+(?:workers|employees|people|personnel)\s+(?:(?:are|were)\s+)?(?:working\s+)?(?:in|inside|within|entering)\b'
    yes_workers = r'\b(?:workers|employees|people|personnel)\s+(?:(?:are|were|will\s+be)\s+)?(?:working\s+)?(?:in|inside|within|entering)\b'
    if _has(no_workers, text):
        add('employees_exposed', False, 'no workers in excavation')
    elif _has(yes_workers, text):
        add('employees_exposed', True, 'workers in excavation')

    if _has(r'\b(?:not|isn.t|aren.t)\s+(?:entirely\s+)?(?:in\s+)?stable\s+rock\b|\bunstable\s+rock\b', text):
        add('stable_rock', False, 'not stable rock')
    elif _has(r'\b(?:entirely|completely|all)\s+in\s+stable\s+rock\b', text):
        add('stable_rock', True, 'entirely in stable rock')

    none = r'\b(?:no|without|lacking)\s+(?:a\s+|any\s+)?(?:cave[- ]in\s+)?(?:protective\s+system|protection|shoring|shield(?:ing)?|trench\s+box)\b|\bunprotected\s+trench\b'
    verified = r'\b(?:verified|engineer[- ]verified)\s+(?:protective\s+system|shoring|trench\s+box)\b|\b(?:protective\s+system|shoring|trench\s+box)\s+(?:is\s+|was\s+)?(?:design[- ]?)?verified\b'
    present = r'\b(?:protective\s+system|shoring|trench\s+box|shield(?:ing)?)\s+(?:is\s+|was\s+)?(?:installed|present|in\s+place)\b|\b(?:installed|using|has)\s+(?:a\s+)?(?:protective\s+system|shoring|trench\s+box)\b'
    if _has(none, text):
        add('protective_system', 'none', 'no protective system')
    elif _has(verified, text):
        add('protective_system', 'verified', 'verified protective system (user claim)')
    elif _has(present, text):
        add('protective_system', 'present_unverified', 'protective system present but unverified')

    if _has(r'\b(?:no|without|lacking)\s+(?:safe\s+)?(?:ladder|egress|exit|ramp|stairway)\b|\b(?:ladder|egress|exit)\s+(?:is\s+)?(?:not|unavailable)\s+within\s+25\s*(?:feet|ft)\b', text):
        add('safe_egress_within_25ft', False, 'no safe egress stated')
    elif _has(r'\b(?:safe\s+)?(?:ladder|ramp|stairway|egress|exit)\s+(?:is\s+|available\s+)?within\s+25\s*(?:feet|ft)\b', text):
        add('safe_egress_within_25ft', True, 'egress within 25 feet (user claim)')

    if _has(r'\b(?:no|without)\s+(?:spoil\s+piles?|excavated\s+material(?:s)?)\b', text):
        add('spoil_hazard', False, 'no spoil piles')
    elif _has(r'\b(?:spoil\s+piles?|excavated\s+material(?:s)?)\s+(?:could\s+)?(?:fall|roll)\s+(?:into|in)\b', text):
        add('spoil_hazard', True, 'spoil fall/roll hazard')

    if _has(r'\b(?:no|without)\s+(?:competent[- ]person\s+)?inspection\s+before\s+(?:work|shift)\b|\bnot\s+inspected\s+before\s+(?:work|shift)\b', text):
        add('inspection_before_work', False, 'no pre-work inspection')
    elif _has(r'\b(?:competent[- ]person\s+)?inspection\s+before\s+(?:work|shift)\s+(?:was\s+)?(?:completed|done|performed)\b', text):
        add('inspection_before_work', True, 'pre-work inspection completed')

    if _has(r'\b(?:no|without)\s+(?:rain|rainstorm|heavy\s+rain)\b', text):
        add('rain_event', False, 'no rain event')
    elif _has(r'\b(?:rainstorm|heavy\s+rain)\s+(?:occurred|happened)\b|\b(?:it\s+rained|after\s+(?:the\s+)?rainstorm)\b', text):
        add('rain_event', True, 'rain event')

    if _has(r'\b(?:competent[- ]person|inspector)\s+(?:has\s+)?(?:examined|inspected)\b.{0,75}\b(?:no\s+(?:indication|risk|sign)\s+of\s+(?:potential\s+)?cave[- ]in|no\s+cave[- ]in\s+(?:hazard|potential))\b', text):
        add('competent_person_no_cave_in', True, 'competent-person examination (user claim)')

    # Layer 5 expansion: never infer the *adequacy* of water precautions from
    # the mere mention of pumping, shields, or water removal equipment.
    if _has(r'\b(?:no\s+(?:standing|accumulated|accumulating)\s+water|water\s+(?:is\s+)?not\s+accumulating|excavation\s+(?:is\s+)?dry)\b', text):
        add('water_accumulating', False, 'no accumulated or accumulating water')
    elif _has(r'\b(?:standing\s+water|accumulated\s+water|accumulating\s+water|water\s+(?:is\s+|has\s+been\s+)?accumulating|flood(?:ed|ing)\s+(?:excavation|trench)|water\s+(?:in|inside)\s+(?:the\s+)?(?:trench|excavation))\b', text):
        add('water_accumulating', True, 'water accumulation reported')

    if _has(r'\b(?:no|without|lacking)\s+(?:adequate\s+)?(?:water[- ]hazard\s+)?(?:protective\s+)?precautions\b|\b(?:adequate\s+)?water\s+precautions\s+(?:were\s+|are\s+)?not\s+(?:taken|in\s+place)\b', text):
        add('water_precautions_adequate', False, 'adequate water precautions reported absent')
    elif _has(r'\b(?:adequate\s+(?:water[- ]hazard\s+)?(?:protective\s+)?precautions\s+(?:are\s+|were\s+|have\s+been\s+)?(?:in\s+place|taken|implemented|verified)|water\s+precautions\s+(?:are\s+|were\s+)?adequate)\b', text):
        add('water_precautions_adequate', True, 'adequate water precautions claimed (not verified)')

    # Utility references convey potential applicability only. Contact and
    # exact-location obligations under 1926.651(b)(2)-(4) are not evaluated.
    if _has(r'\b(?:no|without)\s+(?:underground\s+|buried\s+)?(?:utility\s+installations|utilities|utility\s+lines)\s+(?:are\s+)?(?:expected|anticipated|nearby|present)\b|\bno\s+underground\s+utilities\b', text):
        add('utilities_expected', False, 'no underground utilities expected (user claim)')
    elif _has(r'\b(?:underground\s+utilities|underground\s+utility\s+installations|buried\s+(?:utilities|utility\s+lines)|utility\s+lines)\s+(?:are\s+|were\s+)?(?:nearby|expected|anticipated|present|in\s+(?:the\s+)?area)\b', text):
        add('utilities_expected', True, 'underground utilities expected')

    if _has(r'\b(?:utility\s+(?:locations|installations)|locations\s+of\s+(?:the\s+)?(?:underground\s+)?utilities)\s+(?:have\s+|were\s+|are\s+)?not\s+(?:been\s+)?(?:estimated|determined|identified|located)\b|\b(?:no|without)\s+(?:utility\s+)?location\s+survey\b', text):
        add('utility_locations_estimated', False, 'estimated utility locations not determined')
    elif _has(r'\b(?:utility\s+locations|estimated\s+locations\s+of\s+(?:underground\s+)?utilities|locations\s+of\s+(?:the\s+)?underground\s+utilities)\s+(?:have\s+been\s+|were\s+|are\s+)?(?:estimated|determined|identified)\b', text):
        add('utility_locations_estimated', True, 'estimated utility locations determined (user claim)')

    if _has(r'\b(?:excavation|trench)\s+(?:has\s+)?not\s+(?:been\s+)?opened\b|\b(?:before\s+opening|not\s+yet\s+opened)\s+(?:the\s+)?(?:excavation|trench)\b', text):
        add('excavation_opened', False, 'excavation not yet opened')
    elif _has(r'\b(?:excavation|trench)\s+(?:has\s+been\s+|is\s+|was\s+)?(?:already\s+)?open(?:ed)?\b|\b(?:excavation|trench)\s+(?:has\s+)?(?:already\s+)?begun\b', text):
        add('excavation_opened', True, 'excavation already opened')

    # The underlying CRS engine performs range/type checks.
    if conditions:
        validate_changes(conditions)
    return {'conditions': conditions, 'evidence': evidence,
            'parser': 'deterministic-excavation-v1',
            'limitations': 'Only recognized explicit claims are extracted; missing facts remain unknown.'}
