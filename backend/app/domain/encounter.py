"""Encounter aggregate: the single unit of persistence (stored as one JSON document).
Derived views (workflow stage, note text, documentation-readiness evaluation, export staleness)
are computed on read and are NOT stored here — see app/api/schemas.py.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.facts import SINGLE_VALUED_TYPES, Fact, FactType, ReviewStatus, Speaker, Strict
from app.domain.policy import RequirementStatus


# --------------------------------------------------------------------------- identity & context
class SyntheticPatient(Strict):
    """Demographics come from the fixture and are never inferred by extraction."""

    synthetic_mrn: str = Field(pattern=r"^SYN-\d{6}$")
    given_name: str
    family_name: str
    birth_date: date
    administrative_gender: Literal["male", "female", "other", "unknown"]
    synthetic: Literal[True] = True


class EncounterContext(Strict):
    encounter_date: date
    specialty: Literal["cardiology", "gastroenterology"]
    visit_type: str  # e.g. "Heart failure follow-up"
    clinician_display: str
    location_display: str
    fixture_id: str | None = None


# --------------------------------------------------------------------------- transcript
class TranscriptSegment(Strict):
    id: str = Field(pattern=r"^s\d+$")
    seq: int = Field(ge=1)
    speaker: Speaker
    speaker_label: str  # "Dr. Reyes", "M. Ortiz, MA"
    text: str = Field(min_length=1, max_length=2000)


class Transcript(Strict):
    segments: list[TranscriptSegment] = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def _ordered_unique(self) -> Transcript:
        ids = [s.id for s in self.segments]
        if len(set(ids)) != len(ids):
            raise ValueError("segment ids must be unique")
        if [s.seq for s in self.segments] != list(range(1, len(self.segments) + 1)):
            raise ValueError("segment seq must be 1..n in order")
        return self

    def segment(self, segment_id: str) -> TranscriptSegment | None:
        return next((s for s in self.segments if s.id == segment_id), None)


# --------------------------------------------------------------------------- extraction runs
class ExtractionIssueKind(StrEnum):
    PROVIDER_ERROR = "provider_error"  # timeout, auth, network → run FAILED
    INVALID_JSON = "invalid_json"  # → run FAILED (after retry, real provider only)
    ENVELOPE_INVALID = "envelope_invalid"  # top-level shape wrong → run FAILED
    TOO_MANY_FACTS = "too_many_facts"  # >60 items → run FAILED
    ITEM_INVALID = "item_invalid"  # one fact item fails schema → item dropped
    DISALLOWED_ASSERTION = "disallowed_assertion"  # e.g. negated LVEF → item dropped
    UNKNOWN_SEGMENT = "unknown_segment"  # evidence cites a non-existent segment → evidence dropped
    QUOTE_NOT_FOUND = "quote_not_found"  # quote not in cited segment → evidence dropped
    UNGROUNDED_FACT = "ungrounded_fact"  # all evidence dropped → item dropped


class ExtractionIssue(Strict):
    kind: ExtractionIssueKind
    item_index: int | None = None
    fact_type: str | None = None  # raw string; may be an unknown type
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ExtractionRunStatus(StrEnum):
    SUCCEEDED = "succeeded"  # all items accepted
    SUCCEEDED_WITH_ISSUES = "succeeded_with_issues"  # ≥1 item accepted, ≥1 dropped
    FAILED = "failed"  # nothing usable (provider error, bad JSON/envelope, or zero accepted items with issues)


class ExtractionRun(Strict):
    id: str = Field(pattern=r"^run_[a-z0-9]{10,}$")
    provider: Literal["mock"]
    model: str | None = None
    prompt_version: str
    started_at: datetime
    completed_at: datetime
    attempts: int = Field(ge=1, le=2)
    status: ExtractionRunStatus
    accepted_fact_ids: list[str] = Field(default_factory=list)
    issues: list[ExtractionIssue] = Field(default_factory=list)
    raw_output: str | None = Field(default=None, max_length=200_000)  # last attempt, kept for inspection


# --------------------------------------------------------------------------- note
class NoteSectionKey(StrEnum):
    SUBJECTIVE = "subjective"
    OBJECTIVE = "objective"
    MEDICATIONS = "medications"
    ASSESSMENT_PLAN = "assessment_plan"


class NoteSectionState(Strict):
    """Stored clinician interaction with a note section. Generated text is derived."""

    key: NoteSectionKey
    override_text: str | None = Field(default=None, max_length=8000)
    override_review_revision: int | None = None  # review_revision when override was saved
    override_by: str | None = None
    override_at: datetime | None = None
    accepted_review_revision: int | None = None
    accepted_by: str | None = None
    accepted_at: datetime | None = None


# --------------------------------------------------------------------------- export
class ExportManifestEntry(Strict):
    resource_type: str
    resource_id: str  # urn:uuid:… as used in the bundle
    fact_ids: list[str]  # [] for Patient / Encounter (from context, not facts)


class ExportExclusion(Strict):
    fact_id: str
    reason: str  # e.g. "hypothetical medication is not exported", "symptom facts are not mapped in v1"


class FhirExport(Strict):
    id: str = Field(pattern=r"^exp_[a-z0-9]{10,}$")
    generated_at: datetime
    generated_by: str
    review_revision: int
    bundle: dict[str, Any]
    manifest: list[ExportManifestEntry]
    excluded: list[ExportExclusion]  # approved facts deliberately NOT in the bundle, with reasons


# --------------------------------------------------------------------------- audit
class AuditEventType(StrEnum):
    ENCOUNTER_CREATED = "encounter.created"
    EXTRACTION_COMPLETED = "extraction.completed"  # SUCCEEDED or SUCCEEDED_WITH_ISSUES
    EXTRACTION_FAILED = "extraction.failed"
    FACT_APPROVED = "fact.approved"
    FACT_EDITED = "fact.edited"  # approve with changed value/assertion; payload has before/after
    FACT_REJECTED = "fact.rejected"
    FACT_REOPENED = "fact.reopened"
    FACT_ADDED = "fact.added"  # clinician-origin
    NOTE_SECTION_EDITED = "note.section_edited"
    NOTE_SECTION_REVERTED = "note.section_reverted"
    NOTE_SECTION_ACCEPTED = "note.section_accepted"
    READINESS_CHANGED = "prior_auth.readiness_changed"  # only when ≥1 requirement status changes
    EXPORT_GENERATED = "export.generated"
    EXPORT_BLOCKED = "export.blocked"


class AuditEvent(Strict):
    id: str = Field(pattern=r"^evt_[a-z0-9]{10,}$")
    encounter_id: str
    seq: int = Field(ge=1)  # monotonic per encounter
    at: datetime
    actor_kind: Literal["clinician", "system"]
    actor_display: str  # "Dr. A. Reyes" or "CardioFlow" / "extraction:mock"
    type: AuditEventType
    fact_id: str | None = None
    summary: str  # one human sentence, rendered in the audit drawer
    payload: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- aggregate
class Encounter(Strict):
    id: str = Field(pattern=r"^enc_[a-z0-9]{10,}$")
    created_at: datetime
    updated_at: datetime
    revision: int = Field(ge=0)  # bumps on EVERY mutation; clients send expected_revision
    review_revision: int = Field(ge=0)  # bumps only when approved-fact state changes (drives staleness)
    patient: SyntheticPatient
    context: EncounterContext
    transcript: Transcript
    extraction_runs: list[ExtractionRun] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    note_sections: list[NoteSectionState] = Field(default_factory=list)
    exports: list[FhirExport] = Field(default_factory=list)
    last_requirement_statuses: dict[str, RequirementStatus] = Field(default_factory=dict)  # for READINESS_CHANGED

    @model_validator(mode="after")
    def _single_valued(self) -> Encounter:
        seen: dict[FactType, str] = {}
        for f in self.facts:
            if f.review.status is ReviewStatus.APPROVED and f.fact_type in SINGLE_VALUED_TYPES:
                if f.fact_type in seen:
                    raise ValueError(f"two approved {f.fact_type} facts: {seen[f.fact_type]}, {f.id}")
                seen[f.fact_type] = f.id
        return self
