# mypy: disable-error-code=union-attr
from __future__ import annotations

from app.api.schemas import NoteLine
from app.domain.encounter import NoteSectionKey
from app.domain.facts import Assertion, FactType
from app.policy.engine import ApprovedFactRef


def generate(approved: list[ApprovedFactRef]) -> dict[NoteSectionKey, list[NoteLine]]:
    out: dict[NoteSectionKey, list[NoteLine]] = {k: [] for k in NoteSectionKey}
    for f in approved:
        v = f.approved.value
        suffix = " (uncertain)" if f.approved.assertion is Assertion.UNCERTAIN else ""
        text = None
        key = None
        if f.fact_type is FactType.SYMPTOM:
            label = v.symptom.replace("_", " ")
            detail = f": {v.detail_text}" if v.detail_text else ""
            text = (
                f"Denies {label}."
                if f.approved.assertion is Assertion.NEGATED
                else f"{'Possible' if f.approved.assertion is Assertion.UNCERTAIN else 'Reports'} {label}{detail}."
            )
            key = NoteSectionKey.SUBJECTIVE
        elif f.fact_type is FactType.CONDITION_HISTORY:
            label = v.condition.replace("_", " ")
            text = (
                f"{'Denies prior diagnosis of' if f.approved.assertion is Assertion.NEGATED else 'History of'} {label}."
            )
            key = NoteSectionKey.SUBJECTIVE
        elif f.fact_type is FactType.BLOOD_PRESSURE:
            text = f"BP {v.systolic}/{v.diastolic} mmHg.{suffix}"
            key = NoteSectionKey.OBJECTIVE
        elif f.fact_type is FactType.RESTING_HEART_RATE:
            text = f"Resting HR {v.bpm} bpm.{suffix}"
            key = NoteSectionKey.OBJECTIVE
        elif f.fact_type is FactType.CARDIAC_RHYTHM:
            text = f"Rhythm: {v.rhythm.replace('_', ' ')} ({v.source}).{suffix}"
            key = NoteSectionKey.OBJECTIVE
        elif f.fact_type is FactType.LVEF:
            value = f"{v.percent}{' to ' + str(v.percent_upper) if v.percent_upper else ''}%"
            source = f"{v.modality.replace('_', ' ')}, {v.measured_on_text or 'date not stated'}"
            text = f"LVEF {value} ({source}).{suffix}"
            key = NoteSectionKey.OBJECTIVE
        elif f.fact_type is FactType.MEDICATION:
            dose = v.dose_text or (f"{v.dose_value:g} {v.dose_unit}" if v.dose_value and v.dose_unit else "")
            freq = {"bid": "twice daily", "daily": "daily"}.get(v.frequency, v.frequency)
            if v.status == "planned":
                text = f"Start {v.raw_name} {dose} {freq}."
                key = NoteSectionKey.ASSESSMENT_PLAN
            else:
                text = f"{v.raw_name} {dose} {freq}."
                key = NoteSectionKey.MEDICATIONS
        elif f.fact_type is FactType.HF_DIAGNOSIS:
            text = f"{v.chronicity.replace('_', ' ').title()} {v.hf_type.upper()} documented."
            key = NoteSectionKey.ASSESSMENT_PLAN
        elif f.fact_type is FactType.BETA_BLOCKER_DOSE_STATUS:
            text = f"Beta-blocker: {v.status.replace('_', ' ')}."
            key = NoteSectionKey.ASSESSMENT_PLAN
        if text and key:
            out[key].append(NoteLine(text=text, fact_ids=[f.fact_id]))
    return out
