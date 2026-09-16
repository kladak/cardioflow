from __future__ import annotations

from collections import Counter

from app.api.schemas import (
    EncounterHeader,
    EncounterListItem,
    EncounterView,
    ExportBlockReason,
    ExportStatusView,
    ExportSummary,
    ExtractionSummary,
    FactCounts,
    NoteSectionView,
    WorkflowStage,
)
from app.domain.encounter import Encounter, NoteSectionKey
from app.domain.facts import FactType, ReviewStatus
from app.fhir.mapper import resource_counts
from app.note.generator import generate
from app.policy.engine import ApprovedFactRef, evaluate, load_policy

TITLES = {
    NoteSectionKey.SUBJECTIVE: "Subjective",
    NoteSectionKey.OBJECTIVE: "Objective",
    NoteSectionKey.MEDICATIONS: "Medications",
    NoteSectionKey.ASSESSMENT_PLAN: "Assessment & Plan",
}


def approved_facts(encounter: Encounter) -> list[ApprovedFactRef]:
    return [
        ApprovedFactRef(f.id, f.fact_type, f.origin, f.approved)
        for f in encounter.facts
        if f.review.status is ReviewStatus.APPROVED and f.approved is not None
    ]


def build_view(encounter: Encounter, provider: str = "mock") -> EncounterView:
    counts = Counter(f.review.status.value for f in encounter.facts)
    approved = approved_facts(encounter)
    pending = [(f.id, f.fact_type) for f in encounter.facts if f.review.status is ReviewStatus.PENDING]
    policy = load_policy()
    authorization_applicable = encounter.context.fixture_id in {"hfref_golden", "hfref_ambiguous"}
    prior = evaluate(policy, approved, pending, encounter.context, encounter.review_revision)
    latest = encounter.exports[-1] if encounter.exports else None
    export_summary = (
        ExportSummary(
            id=latest.id,
            generated_at=latest.generated_at,
            generated_by=latest.generated_by,
            review_revision=latest.review_revision,
            is_stale=latest.review_revision != encounter.review_revision,
            resource_counts=resource_counts(latest.bundle),
        )
        if latest
        else None
    )
    blocked = []
    if pending:
        blocked.append(
            ExportBlockReason(
                code="pending_facts", message=f"{len(pending)} findings still pending", fact_ids=[x[0] for x in pending]
            )
        )
    if not approved:
        blocked.append(ExportBlockReason(code="no_approved_facts", message="At least one finding must be approved"))
    export = ExportStatusView(can_export=not blocked, blocked_reasons=blocked, latest=export_summary)
    if latest and latest.review_revision == encounter.review_revision:
        stage = WorkflowStage.EXPORTED
    elif encounter.facts and not pending:
        stage = WorkflowStage.REVIEW_COMPLETE
    elif pending:
        stage = WorkflowStage.IN_REVIEW
    elif encounter.extraction_runs and encounter.extraction_runs[-1].status.value == "failed":
        stage = WorkflowStage.EXTRACTION_FAILED
    else:
        stage = WorkflowStage.TRANSCRIPT_READY
    generated = generate(approved)
    stored = {s.key: s for s in encounter.note_sections}
    note = []
    feeds = {
        NoteSectionKey.SUBJECTIVE: {"symptom", "condition_history"},
        NoteSectionKey.OBJECTIVE: {"lvef", "resting_heart_rate", "blood_pressure", "cardiac_rhythm"},
        NoteSectionKey.MEDICATIONS: {"medication"},
        NoteSectionKey.ASSESSMENT_PLAN: {
            "hf_diagnosis",
            "lvef",
            "nyha_class",
            "beta_blocker_dose_status",
            "medication",
        },
    }
    for key in NoteSectionKey:
        state = stored.get(key)
        lines = generated[key]
        override = state.override_text if state else None
        note.append(
            NoteSectionView(
                key=key,
                title=TITLES[key],
                generated_lines=lines,
                pending_fact_count=sum(
                    1
                    for f in encounter.facts
                    if f.review.status is ReviewStatus.PENDING and f.fact_type.value in feeds[key]
                ),
                is_overridden=override is not None,
                override_text=override,
                override_stale=bool(
                    state and override is not None and (state.override_review_revision or 0) < encounter.review_revision
                ),
                effective_text=override if override is not None else "\n".join(x.text for x in lines),
                accepted=bool(state and state.accepted_review_revision is not None),
                acceptance_stale=bool(
                    state
                    and state.accepted_review_revision is not None
                    and state.accepted_review_revision < encounter.review_revision
                ),
            )
        )
    facts = sorted(
        encounter.facts,
        key=lambda f: (
            list(FactType).index(f.fact_type),
            f.candidate.evidence[0].segment_id if f.candidate else "z",
        ),
    )
    fc = FactCounts(
        total=len(facts),
        pending=counts["pending"],
        pending_flagged=sum(
            1 for f in facts if f.review.status is ReviewStatus.PENDING and f.candidate and f.candidate.flags
        ),
        approved=counts["approved"],
        approved_edited=sum(1 for f in facts if f.approved and f.approved.edited),
        rejected=counts["rejected"],
    )
    can_run = not any(f.review.status is not ReviewStatus.PENDING or f.origin.value == "clinician" for f in facts)
    return EncounterView(
        encounter=EncounterHeader(
            id=encounter.id,
            created_at=encounter.created_at,
            updated_at=encounter.updated_at,
            revision=encounter.revision,
            review_revision=encounter.review_revision,
            patient=encounter.patient,
            context=encounter.context,
        ),
        stage=stage,
        transcript=encounter.transcript,
        extraction=ExtractionSummary(
            latest_run=encounter.extraction_runs[-1] if encounter.extraction_runs else None,
            run_count=len(encounter.extraction_runs),
            can_run=can_run,
            provider=provider,
        ),
        facts=facts,
        fact_counts=fc,
        note_sections=note,
        prior_auth=prior,
        authorization_policy=policy if authorization_applicable else None,
        export=export,
    )


def list_item(e: Encounter) -> EncounterListItem:
    view = build_view(e)
    return EncounterListItem(
        id=e.id,
        patient_display=f"{e.patient.family_name}, {e.patient.given_name} ({e.patient.synthetic_mrn})",
        encounter_date=e.context.encounter_date.isoformat(),
        visit_type=e.context.visit_type,
        stage=view.stage,
        readiness=view.prior_auth.overall,
        authorization_applicable=e.context.fixture_id in {"hfref_golden", "hfref_ambiguous"},
        updated_at=e.updated_at,
    )
