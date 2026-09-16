# mypy: disable-error-code="union-attr,assignment,comparison-overlap"
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.encounter import EncounterContext
from app.domain.facts import DRUG_CLASS, ApprovedFact, Assertion, Drug, DrugClass, FactOrigin, FactType, Speaker
from app.domain.policy import (
    AuthorizationPolicy,
    OverallReadiness,
    PriorAuthEvaluation,
    RequirementEvaluation,
    RequirementStatus,
)
from app.policy.dates import resolve_spoken_date


@dataclass(frozen=True)
class ApprovedFactRef:
    fact_id: str
    fact_type: FactType
    origin: FactOrigin
    approved: ApprovedFact


def load_policy() -> AuthorizationPolicy:
    path = Path(__file__).parent / "policies" / "sim_ivabradine_hfref_v1.json"
    return AuthorizationPolicy.model_validate_json(path.read_text())


def _patient_only(ref: ApprovedFactRef) -> bool:
    return (
        ref.origin is FactOrigin.EXTRACTION
        and bool(ref.approved.evidence)
        and all(e.speaker is Speaker.PATIENT for e in ref.approved.evidence)
    )


def evaluate(
    policy: AuthorizationPolicy,
    approved: list[ApprovedFactRef],
    pending: list[tuple[str, FactType]],
    context: EncounterContext,
    review_revision: int,
) -> PriorAuthEvaluation:
    def by_type(fact_type: FactType) -> list[ApprovedFactRef]:
        return [fact for fact in approved if fact.fact_type is fact_type]

    results: list[RequirementEvaluation] = []
    for req in policy.requirements:
        pending_ids = [fid for fid, ft in pending if ft in req.fact_types]
        used: list[str] = []
        status = RequirementStatus.MISSING
        explanation = f"No approved documentation for {req.title.lower()}."
        if req.id == "R2":
            status = (
                RequirementStatus.SATISFIED
                if context.specialty == req.params["specialty"]
                else RequirementStatus.NOT_MET
            )
            explanation = (
                "Encounter specialty is cardiology."
                if status is RequirementStatus.SATISFIED
                else "Encounter specialty is not cardiology."
            )
        elif req.id == "R1":
            refs = [
                f
                for f in by_type(FactType.MEDICATION)
                if f.approved.value.drug is Drug.IVABRADINE and f.approved.value.status == "planned"
            ]
            if refs:
                used = [refs[0].fact_id]
                status = (
                    RequirementStatus.SATISFIED
                    if refs[0].approved.assertion is Assertion.AFFIRMED
                    else RequirementStatus.REQUIRES_REVIEW
                )
                explanation = (
                    "A decided plan to start ivabradine is documented."
                    if status is RequirementStatus.SATISFIED
                    else "Ivabradine is mentioned as a possibility, not a decided plan."
                )
        elif req.id == "R3":
            refs = by_type(FactType.HF_DIAGNOSIS)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                v = f.approved.value
                if (
                    f.approved.assertion is not Assertion.AFFIRMED
                    or v.hf_type == "unspecified"
                    or v.chronicity in {"unspecified", "acute_on_chronic"}
                ):
                    status = RequirementStatus.REQUIRES_REVIEW
                elif v.hf_type != "hfref" or v.chronicity == "acute":
                    status = RequirementStatus.NOT_MET
                else:
                    status = RequirementStatus.SATISFIED
                explanation = {
                    RequirementStatus.SATISFIED: "Chronic HFrEF is documented.",
                    RequirementStatus.NOT_MET: "The approved diagnosis does not meet the chronic HFrEF criterion.",
                    RequirementStatus.REQUIRES_REVIEW: "Heart-failure type or chronicity needs clinician review.",
                }[status]
        elif req.id == "R4":
            refs = by_type(FactType.LVEF)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                v = f.approved.value
                resolved = resolve_spoken_date(v.measured_on_text, context.encounter_date)
                patient = _patient_only(f)
                if (
                    f.approved.assertion is not Assertion.AFFIRMED
                    or patient
                    or not resolved
                    or (v.percent_upper is not None and v.percent_upper > 35)
                ):
                    status = RequirementStatus.REQUIRES_REVIEW
                elif v.percent > 35 or (context.encounter_date - resolved).days > 365:
                    status = RequirementStatus.NOT_MET
                else:
                    status = RequirementStatus.SATISFIED
                if status is RequirementStatus.SATISFIED:
                    explanation = f"LVEF {v.percent}% ({v.modality}, {resolved.isoformat()}) is at or below 35%."
                elif status is RequirementStatus.NOT_MET:
                    explanation = f"LVEF {v.percent}% or its measurement date does not meet the criterion."
                else:
                    explanation = "LVEF needs review because the source, certainty, range, or date is insufficient."
        elif req.id == "R5":
            refs = by_type(FactType.NYHA_CLASS)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                v = f.approved.value
                vals = {v.nyha, v.nyha_upper} - {None}
                if (
                    f.approved.assertion is not Assertion.AFFIRMED
                    or "IV" in vals
                    or len(vals & {"I"})
                    and len(vals) > 1
                ):
                    status = RequirementStatus.REQUIRES_REVIEW
                elif vals <= {"II", "III"}:
                    status = RequirementStatus.SATISFIED
                else:
                    status = RequirementStatus.NOT_MET
                ordered = [item for item in ("I", "II", "III", "IV") if item in vals]
                explanation = (
                    f"NYHA class {'–'.join(ordered)} is documented."
                    if status is RequirementStatus.SATISFIED
                    else "Approved NYHA class needs review or does not meet the criterion."
                )
        elif req.id == "R6":
            refs = by_type(FactType.CARDIAC_RHYTHM)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                v = f.approved.value
                hist = [
                    h
                    for h in by_type(FactType.CONDITION_HISTORY)
                    if h.approved.value.condition in {"atrial_fibrillation", "atrial_flutter"}
                    and h.approved.assertion is not Assertion.NEGATED
                ]
                used += [h.fact_id for h in hist]
                if (
                    f.approved.assertion is not Assertion.AFFIRMED
                    or _patient_only(f)
                    or v.rhythm == "other"
                    or v.source not in {"ecg", "monitor"}
                    or hist
                ):
                    status = RequirementStatus.REQUIRES_REVIEW
                elif v.rhythm != "sinus":
                    status = RequirementStatus.NOT_MET
                else:
                    status = RequirementStatus.SATISFIED
                explanation = {
                    RequirementStatus.SATISFIED: "Sinus rhythm is documented by ECG.",
                    RequirementStatus.NOT_MET: f"Approved rhythm is {v.rhythm.replace('_', ' ')}.",
                    RequirementStatus.REQUIRES_REVIEW: "Rhythm documentation needs clinician review.",
                }[status]
        elif req.id == "R7":
            refs = by_type(FactType.RESTING_HEART_RATE)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                bpm = f.approved.value.bpm
                if f.approved.assertion is not Assertion.AFFIRMED or _patient_only(f):
                    status = RequirementStatus.REQUIRES_REVIEW
                else:
                    status = RequirementStatus.SATISFIED if bpm >= 70 else RequirementStatus.NOT_MET
                comparison = "at or above" if status is RequirementStatus.SATISFIED else "below"
                explanation = (
                    f"Resting heart rate {bpm} bpm is {comparison} 70 bpm."
                    if status is not RequirementStatus.REQUIRES_REVIEW
                    else "Resting heart rate needs review."
                )
        elif req.id == "R8":
            refs = by_type(FactType.BETA_BLOCKER_DOSE_STATUS)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                status_value = f.approved.value.status
                if f.approved.assertion is not Assertion.AFFIRMED:
                    status = RequirementStatus.REQUIRES_REVIEW
                elif status_value == "below_max_tolerated_dose":
                    status = RequirementStatus.NOT_MET
                else:
                    status = RequirementStatus.SATISFIED
                explanation = (
                    "Beta-blocker optimization is documented."
                    if status is RequirementStatus.SATISFIED
                    else "Beta-blocker dose status needs review or does not meet the criterion."
                )
            else:
                meds = [
                    f
                    for f in by_type(FactType.MEDICATION)
                    if DRUG_CLASS.get(f.approved.value.drug) is DrugClass.BETA_BLOCKER
                    and f.approved.value.status == "active"
                ]
                if meds:
                    used = [meds[0].fact_id]
                    status = RequirementStatus.REQUIRES_REVIEW
                    explanation = f"On {meds[0].approved.value.raw_name}; maximum-tolerated dose not documented."
        elif req.id == "R9":
            refs = by_type(FactType.BLOOD_PRESSURE)
            if refs:
                f = refs[0]
                used = [f.fact_id]
                v = f.approved.value
                if f.approved.assertion is not Assertion.AFFIRMED or _patient_only(f):
                    status = RequirementStatus.REQUIRES_REVIEW
                else:
                    status = (
                        RequirementStatus.SATISFIED
                        if v.systolic >= 90 and v.diastolic >= 50
                        else RequirementStatus.NOT_MET
                    )
                comparison = "at or above" if status is RequirementStatus.SATISFIED else "below"
                explanation = (
                    f"Blood pressure {v.systolic}/{v.diastolic} mmHg is {comparison} 90/50 mmHg."
                    if status is not RequirementStatus.REQUIRES_REVIEW
                    else "Blood pressure needs review."
                )
        results.append(
            RequirementEvaluation(
                requirement_id=req.id,
                status=status,
                explanation=explanation,
                used_fact_ids=used,
                pending_fact_ids=pending_ids,
                missing_fact_types=req.fact_types if status is RequirementStatus.MISSING else [],
                context_fields_used=["context.specialty"] if req.id == "R2" else [],
            )
        )
    statuses = {r.status for r in results}
    overall = (
        OverallReadiness.NOT_MET
        if RequirementStatus.NOT_MET in statuses
        else OverallReadiness.INCOMPLETE
        if RequirementStatus.MISSING in statuses
        else OverallReadiness.NEEDS_REVIEW
        if RequirementStatus.REQUIRES_REVIEW in statuses
        else OverallReadiness.READY
    )
    return PriorAuthEvaluation(
        policy_id=policy.id,
        policy_version=policy.version,
        review_revision=review_revision,
        overall=overall,
        requirements=results,
    )
