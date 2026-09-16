from __future__ import annotations

import re

from app.domain.facts import (
    MEASUREMENT_TYPES,
    NUMERIC_GROUNDING_FIELDS,
    Assertion,
    CandidateFact,
    FactType,
    ModelConfidence,
    ReviewFlag,
    Speaker,
)

HEDGES = (
    "maybe",
    "i think",
    "not sure",
    "probably",
    "about",
    "around",
    "like",
    "might",
    "possibly",
    "or so",
    "don't remember",
    "i guess",
    "roughly",
    "approximately",
)


def compute_flags(
    fact_type: FactType, candidate: CandidateFact, peers: list[tuple[FactType, CandidateFact]]
) -> list[ReviewFlag]:
    result: list[ReviewFlag] = []
    quotes = " ".join(e.quote for e in candidate.evidence).casefold().replace("’", "'")
    if candidate.model_confidence is ModelConfidence.LOW:
        result.append(ReviewFlag.MODEL_LOW_CONFIDENCE)
    fields = NUMERIC_GROUNDING_FIELDS.get(fact_type, ())
    values = [getattr(candidate.value, field) for field in fields if getattr(candidate.value, field, None) is not None]
    digits = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", quotes)}
    if values and any(float(v) not in digits for v in values):
        result.append(ReviewFlag.VALUE_NOT_IN_EVIDENCE)
    if any(re.search(rf"\b{re.escape(h)}\b", quotes) for h in HEDGES):
        result.append(ReviewFlag.HEDGED_LANGUAGE)
    if (
        fact_type in MEASUREMENT_TYPES
        and candidate.evidence
        and all(e.speaker is Speaker.PATIENT for e in candidate.evidence)
    ):
        result.append(ReviewFlag.PATIENT_REPORTED_MEASUREMENT)
    if fact_type in {
        FactType.HF_DIAGNOSIS,
        FactType.LVEF,
        FactType.NYHA_CLASS,
        FactType.RESTING_HEART_RATE,
        FactType.BLOOD_PRESSURE,
        FactType.CARDIAC_RHYTHM,
        FactType.BETA_BLOCKER_DOSE_STATUS,
    } and any(t is fact_type and c.value != candidate.value for t, c in peers):
        result.append(ReviewFlag.CONFLICTING_CANDIDATES)
    if candidate.assertion in {Assertion.UNCERTAIN, Assertion.HYPOTHETICAL}:
        result.append(ReviewFlag.UNCERTAIN_OR_HYPOTHETICAL)
    if candidate.evidence and all(e.quote.rstrip().endswith("?") for e in candidate.evidence):
        result.append(ReviewFlag.EVIDENCE_IS_QUESTION)
    order = list(ReviewFlag)
    return sorted(set(result), key=order.index)
