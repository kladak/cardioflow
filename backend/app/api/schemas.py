"""HTTP contract. Request bodies + the EncounterView returned by every encounter
read AND every successful mutation (the UI replaces its cache with the response).

Error envelope for all 4xx/5xx: {"error": {"code": ErrorCode, "message": str, "details": {...}}}
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from app.domain.encounter import (
    EncounterContext,
    ExportExclusion,
    ExportManifestEntry,
    ExtractionRun,
    NoteSectionKey,
    SyntheticPatient,
    Transcript,
)
from app.domain.facts import Assertion, Fact, FactType, Strict
from app.domain.policy import AuthorizationPolicy, PriorAuthEvaluation


# --------------------------------------------------------------------------- errors
class ErrorCode(StrEnum):
    NOT_FOUND = "not_found"  # 404
    VALIDATION_ERROR = "validation_error"  # 422 (request body / value schema)
    REVISION_CONFLICT = "revision_conflict"  # 409 expected_revision != current
    INVALID_TRANSITION = "invalid_transition"  # 409 e.g. approve an already-approved fact without edit
    SINGLE_VALUE_CONFLICT = "single_value_conflict"  # 409 details.approved_fact_id
    EXTRACTION_NOT_ALLOWED = "extraction_not_allowed"  # 409 facts already reviewed
    EXPORT_BLOCKED = "export_blocked"  # 409 details.blocked_reasons
    TRANSCRIPT_PARSE_ERROR = "transcript_parse_error"  # 422 details.line
    UNKNOWN_FIXTURE = "unknown_fixture"  # 404


class ErrorBody(Strict):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(Strict):
    error: ErrorBody


# --------------------------------------------------------------------------- requests
class CreateEncounterRequest(Strict):
    """Exactly one of fixture_id or (patient + context + transcript_text)."""

    fixture_id: str | None = None
    patient: SyntheticPatient | None = None
    context: EncounterContext | None = None
    transcript_text: str | None = Field(
        default=None,
        max_length=100_000,
        description="Lines of 'CLINICIAN: …' | 'PATIENT: …' | 'STAFF: …' | 'OTHER: …'. Blank lines ignored.",
    )


class RunExtractionRequest(Strict):
    expected_revision: int


class FactReviewAction(StrEnum):
    APPROVE = "approve"  # pending → approved, value = candidate value
    APPROVE_WITH_EDIT = "approve_with_edit"  # pending|approved → approved, value/assertion from request
    REJECT = "reject"  # pending|approved → rejected
    REOPEN = "reopen"  # approved|rejected → pending (extraction-origin only)


class ReviewFactRequest(Strict):
    expected_revision: int
    action: FactReviewAction
    value: dict[str, Any] | None = None  # required for approve_with_edit; validated with parse_value(fact_type)
    assertion: Assertion | None = None  # optional for approve_with_edit (defaults to candidate/current)
    reason: str | None = Field(default=None, max_length=280)  # required for reject


class AddFactRequest(Strict):
    expected_revision: int
    fact_type: FactType
    value: dict[str, Any]
    assertion: Assertion = Assertion.AFFIRMED
    attestation_note: str = Field(min_length=3, max_length=280)  # "Per echo report 2026-06-12 in EHR"


class NoteSectionAction(StrEnum):
    EDIT = "edit"
    REVERT_TO_GENERATED = "revert_to_generated"
    ACCEPT = "accept"


class NoteSectionRequest(Strict):
    expected_revision: int
    action: NoteSectionAction
    text: str | None = Field(default=None, max_length=8000)  # required for edit


class CreateExportRequest(Strict):
    expected_revision: int


# --------------------------------------------------------------------------- views
class WorkflowStage(StrEnum):
    """Derived, never stored. Evaluated top to bottom; first match wins."""

    EXPORTED = "exported"  # latest export exists and export.review_revision == encounter.review_revision
    REVIEW_COMPLETE = "review_complete"  # ≥1 fact and 0 pending
    IN_REVIEW = "in_review"  # ≥1 pending fact
    EXTRACTION_FAILED = "extraction_failed"  # latest run FAILED and no facts
    TRANSCRIPT_READY = "transcript_ready"  # otherwise (no runs, or succeeded with 0 facts)


class FactCounts(Strict):
    total: int
    pending: int
    pending_flagged: int
    approved: int
    approved_edited: int
    rejected: int


class ExtractionSummary(Strict):
    latest_run: ExtractionRun | None
    run_count: int
    can_run: bool  # False once any fact has been reviewed or clinician-added
    provider: Literal["mock", "anthropic"]  # the configured provider for the next run


class NoteLine(Strict):
    text: str
    fact_ids: list[str]


class NoteSectionView(Strict):
    key: NoteSectionKey
    title: str
    generated_lines: list[NoteLine]  # from approved facts at current review_revision
    pending_fact_count: int  # pending facts whose type feeds this section (UI hint, not note text)
    is_overridden: bool
    override_text: str | None
    override_stale: bool  # overridden and review_revision > override_review_revision
    effective_text: str  # override_text if overridden else "\n".join(generated_lines.text)
    accepted: bool
    acceptance_stale: bool  # accepted and review_revision > accepted_review_revision


class ExportBlockReason(Strict):
    code: Literal["pending_facts", "no_approved_facts"]
    message: str
    fact_ids: list[str] = Field(default_factory=list)


class ExportSummary(Strict):
    id: str
    generated_at: datetime
    generated_by: str
    review_revision: int
    is_stale: bool
    resource_counts: dict[str, int]


class ExportStatusView(Strict):
    can_export: bool
    blocked_reasons: list[ExportBlockReason]
    latest: ExportSummary | None


class EncounterHeader(Strict):
    id: str
    created_at: datetime
    updated_at: datetime
    revision: int
    review_revision: int
    patient: SyntheticPatient
    context: EncounterContext


class EncounterView(Strict):
    encounter: EncounterHeader
    stage: WorkflowStage
    transcript: Transcript
    extraction: ExtractionSummary
    facts: list[Fact]  # ordered by fact-type catalog order, then first evidence segment seq
    fact_counts: FactCounts
    note_sections: list[NoteSectionView]  # fixed order: subjective, objective, medications, assessment_plan
    prior_auth: PriorAuthEvaluation  # computed live from approved facts
    authorization_policy: AuthorizationPolicy | None
    export: ExportStatusView


class EncounterListItem(Strict):
    id: str
    patient_display: str  # "Varga, Ellis (SYN-000142)"
    encounter_date: str
    visit_type: str
    stage: WorkflowStage
    readiness: str  # OverallReadiness value
    authorization_applicable: bool
    updated_at: datetime


class FixtureListItem(Strict):
    id: str
    title: str
    description: str
    purpose: Literal["golden", "adversarial", "simulation"]


class ExportDetail(Strict):
    id: str
    generated_at: datetime
    generated_by: str
    review_revision: int
    is_stale: bool
    bundle: dict[str, Any]
    manifest: list[ExportManifestEntry]
    excluded: list[ExportExclusion]


class PolicyView(Strict):
    policy: AuthorizationPolicy
