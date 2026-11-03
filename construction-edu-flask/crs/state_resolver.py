"""Apply extracted factual corrections to the versioned CRS engine."""
from __future__ import annotations

import re
from crs_engine import CRSInputError
from .extractor import extract_conditions
from .osha_retriever import retrieve_osha

_HYPOTHETICAL = re.compile(r'\b(?:what\s+if|suppose|hypothetically|imagine\s+that)\b', re.I)


def create_from_text(engine, text):
    parsed = extract_conditions(text)
    if not parsed['conditions']:
        raise CRSInputError('No supported excavation conditions found; clarify the scenario')
    scenario = engine.create(parsed['conditions'])
    return {'extraction': parsed, 'scenario': scenario,
            'osha_retrieval': retrieve_osha(query=text, conditions=scenario['conditions'])}


def revise_from_text(engine, scenario_id, text, expected_version, branch='base'):
    if type(expected_version) is not int or expected_version < 1:
        raise CRSInputError('expected_version must be a positive integer')
    if _HYPOTHETICAL.search(text if isinstance(text, str) else '') and branch == 'base':
        raise CRSInputError('Hypothetical statements require a named scenario branch')
    parsed = extract_conditions(text)
    if not parsed['conditions']:
        raise CRSInputError('No supported factual changes found; clarify the correction')
    revised = engine.revise(scenario_id, parsed['conditions'], branch, expected_version)
    return {'extraction': parsed, 'scenario': revised,
            'osha_retrieval': retrieve_osha(query=text, conditions=revised['conditions'])}
