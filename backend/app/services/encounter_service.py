# mypy: disable-error-code="no-untyped-def,type-arg,union-attr"
from __future__ import annotations

from app.api.schemas import (
    CreateEncounterRequest,
    FactReviewAction,
    NoteSectionAction,
    NoteSectionRequest,
    ReviewFactRequest,
)
from app.core.clock import Clock
from app.domain.encounter import (
    AuditEvent,
    AuditEventType,
    Encounter,
    FhirExport,
    NoteSectionKey,
    NoteSectionState,
    Transcript,
)
from app.domain.facts import ApprovedFact, Fact, FactOrigin, ReviewState, ReviewStatus, assertion_allowed, parse_value
from app.extraction.pipeline import run_extraction
from app.fhir.mapper import build_bundle, resource_counts
from app.policy.engine import evaluate, load_policy
from app.services.fixtures import fixture_data
from app.services.view_builder import approved_facts, build_view
from app.store.sqlite import SQLiteStore


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, details: dict | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class EncounterService:
    def __init__(self, store: SQLiteStore, provider, clock: Clock, id_fn, clinician: str):
        self.store = store
        self.provider = provider
        self.clock = clock
        self.id_fn = id_fn
        self.clinician = clinician

    def _event(
        self,
        e: Encounter,
        kind: AuditEventType,
        summary: str,
        fact_id=None,
        payload=None,
        actor="clinician",
        seq_offset=0,
    ) -> AuditEvent:
        return AuditEvent(
            id=self.id_fn("evt"),
            encounter_id=e.id,
            seq=len(self.store.list_audit(e.id)) + 1 + seq_offset,
            at=self.clock.now(),
            actor_kind="system" if actor == "system" else "clinician",
            actor_display="CardioFlow" if actor == "system" else self.clinician,
            type=kind,
            fact_id=fact_id,
            summary=summary,
            payload=payload or {},
        )

    def create(self, req: CreateEncounterRequest):
        try:
            raw = fixture_data(req.fixture_id)
        except KeyError:
            raise ServiceError("unknown_fixture", f"Unknown fixture: {req.fixture_id}", 404) from None
        now = self.clock.now()
        e = Encounter(
            id=self.id_fn("enc"),
            created_at=now,
            updated_at=now,
            revision=0,
            review_revision=0,
            patient=raw["patient"],
            context=raw["context"],
            transcript=Transcript(segments=raw["segments"]),
        )
        event = AuditEvent(
            id=self.id_fn("evt"),
            encounter_id=e.id,
            seq=1,
            at=now,
            actor_kind="clinician",
            actor_display=self.clinician,
            type=AuditEventType.ENCOUNTER_CREATED,
            summary="Synthetic encounter created.",
            payload={"fixture_id": req.fixture_id, "segment_count": len(e.transcript.segments)},
        )
        self.store.create(e, [event])
        return build_view(e)

    def extract(self, encounter_id: str, expected_revision: int):
        e = self.store.load(encounter_id)
        if e.revision != expected_revision:
            raise ServiceError(
                "revision_conflict", "This encounter changed elsewhere.", 409, {"current_revision": e.revision}
            )
        if not build_view(e).extraction.can_run:
            raise ServiceError("extraction_not_allowed", "Extraction is locked after review begins.")
        run, facts = run_extraction(e, self.provider, self.clock.now(), self.id_fn)
        e.facts = [
            f for f in e.facts if not (f.origin is FactOrigin.EXTRACTION and f.review.status is ReviewStatus.PENDING)
        ] + facts
        e.extraction_runs.append(run)
        e.revision += 1
        e.updated_at = self.clock.now()
        kind = AuditEventType.EXTRACTION_FAILED if run.status.value == "failed" else AuditEventType.EXTRACTION_COMPLETED
        event = self._event(
            e,
            kind,
            f"Extraction {run.status.value.replace('_', ' ')}: {len(facts)} findings proposed.",
            payload={"accepted_count": len(facts), "issue_count": len(run.issues)},
            actor="system",
        )
        self.store.save(e, [event], expected_revision)
        return build_view(e)

    def review(self, encounter_id: str, fact_id: str, req: ReviewFactRequest):
        e = self.store.load(encounter_id)
        if e.revision != req.expected_revision:
            raise ServiceError(
                "revision_conflict", "This encounter changed elsewhere.", 409, {"current_revision": e.revision}
            )
        f = next((x for x in e.facts if x.id == fact_id), None)
        if not f:
            raise ServiceError("not_found", "Finding not found.", 404)
        prior_status = f.review.status
        before = f.approved
        now = self.clock.now()
        delta = 0
        if req.action is FactReviewAction.APPROVE:
            if prior_status is not ReviewStatus.PENDING or not f.candidate:
                raise ServiceError("invalid_transition", "This finding cannot be approved from its current state.")
            self._ensure_slot(e, f)
            f.approved = ApprovedFact(
                value=f.candidate.value,
                assertion=f.candidate.assertion,
                evidence=f.candidate.evidence,
                edited=False,
                approved_by=self.clinician,
                approved_at=now,
            )
            f.review = ReviewState(status=ReviewStatus.APPROVED, decided_by=self.clinician, decided_at=now)
            delta = 1
            kind = AuditEventType.FACT_APPROVED
            summary = f"Approved {f.fact_type.value.replace('_', ' ')}."
        elif req.action is FactReviewAction.APPROVE_WITH_EDIT:
            if prior_status not in {ReviewStatus.PENDING, ReviewStatus.APPROVED}:
                raise ServiceError("invalid_transition", "This finding cannot be edited from its current state.")
            if req.value is None:
                raise ServiceError("validation_error", "A typed value is required.", 422)
            try:
                value = parse_value(f.fact_type, req.value)
            except Exception as exc:
                raise ServiceError(
                    "validation_error", "The edited value is invalid.", 422, {"errors": str(exc)}
                ) from exc
            assertion = req.assertion or (f.approved.assertion if f.approved else f.candidate.assertion)
            if not assertion_allowed(f.fact_type, value, assertion):
                raise ServiceError("validation_error", "Assertion is not allowed for this finding.", 422)
            self._ensure_slot(e, f)
            evidence = f.candidate.evidence if f.candidate else []
            edited = bool(f.candidate and (value != f.candidate.value or assertion != f.candidate.assertion))
            f.approved = ApprovedFact(
                value=value,
                assertion=assertion,
                evidence=evidence,
                edited=edited,
                attestation_note=f.approved.attestation_note if f.approved else None,
                approved_by=self.clinician,
                approved_at=now,
            )
            f.review = ReviewState(status=ReviewStatus.APPROVED, decided_by=self.clinician, decided_at=now)
            delta = 1
            kind = AuditEventType.FACT_EDITED
            summary = f"Edited and approved {f.fact_type.value.replace('_', ' ')}."
        elif req.action is FactReviewAction.REJECT:
            if prior_status not in {ReviewStatus.PENDING, ReviewStatus.APPROVED}:
                raise ServiceError("invalid_transition", "This finding is already rejected.")
            f.approved = None
            f.review = ReviewState(
                status=ReviewStatus.REJECTED, decided_by=self.clinician, decided_at=now, rejection_reason=req.reason
            )
            delta = 1 if prior_status is ReviewStatus.APPROVED else 0
            kind = AuditEventType.FACT_REJECTED
            summary = f"Rejected {f.fact_type.value.replace('_', ' ')}."
        else:
            if f.origin is FactOrigin.CLINICIAN or prior_status not in {ReviewStatus.APPROVED, ReviewStatus.REJECTED}:
                raise ServiceError("invalid_transition", "This finding cannot be reopened.")
            f.approved = None
            f.review = ReviewState(status=ReviewStatus.PENDING)
            delta = 1 if prior_status is ReviewStatus.APPROVED else 0
            kind = AuditEventType.FACT_REOPENED
            summary = f"Reopened {f.fact_type.value.replace('_', ' ')}."
        e.revision += 1
        e.review_revision += delta
        e.updated_at = now
        events = [
            self._event(
                e,
                kind,
                summary,
                f.id,
                {
                    "before": before.model_dump(mode="json") if before else None,
                    "after": f.approved.model_dump(mode="json") if f.approved else None,
                },
            )
        ]
        events += self._readiness_event(e)
        self.store.save(e, events, req.expected_revision)
        return build_view(e)

    def _ensure_slot(self, e: Encounter, target: Fact):
        from app.domain.facts import SINGLE_VALUED_TYPES

        if target.fact_type in SINGLE_VALUED_TYPES:
            other = next(
                (
                    f
                    for f in e.facts
                    if f.id != target.id
                    and f.fact_type is target.fact_type
                    and f.review.status is ReviewStatus.APPROVED
                ),
                None,
            )
            if other:
                raise ServiceError(
                    "single_value_conflict",
                    f"An approved {target.fact_type.value} already exists.",
                    409,
                    {"approved_fact_id": other.id},
                )

    def _readiness_event(self, e: Encounter):
        if e.context.fixture_id not in {"hfref_golden", "hfref_ambiguous"}:
            return []
        prior = evaluate(
            load_policy(),
            approved_facts(e),
            [(f.id, f.fact_type) for f in e.facts if f.review.status is ReviewStatus.PENDING],
            e.context,
            e.review_revision,
        )
        current = {r.requirement_id: r.status for r in prior.requirements}
        changes = [
            {"requirement_id": k, "from": e.last_requirement_statuses.get(k, "MISSING"), "to": v}
            for k, v in current.items()
            if e.last_requirement_statuses.get(k) != v
        ]
        e.last_requirement_statuses = current
        return (
            [
                self._event(
                    e,
                    AuditEventType.READINESS_CHANGED,
                    f"Documentation readiness is now {prior.overall.value.replace('_', ' ').title()}.",
                    payload={"overall": prior.overall, "changes": changes},
                    actor="system",
                    seq_offset=1,
                )
            ]
            if changes
            else []
        )

    def note_action(self, encounter_id: str, key: NoteSectionKey, req: NoteSectionRequest):
        e = self.store.load(encounter_id)
        if e.revision != req.expected_revision:
            raise ServiceError(
                "revision_conflict", "This encounter changed elsewhere.", 409, {"current_revision": e.revision}
            )
        state = next((s for s in e.note_sections if s.key is key), None)
        if not state:
            state = NoteSectionState(key=key)
            e.note_sections.append(state)
        now = self.clock.now()
        if req.action is NoteSectionAction.EDIT:
            if req.text is None:
                raise ServiceError("validation_error", "Note text is required.", 422)
            state.override_text = req.text
            state.override_review_revision = e.review_revision
            state.override_by = self.clinician
            state.override_at = now
            kind = AuditEventType.NOTE_SECTION_EDITED
        elif req.action is NoteSectionAction.REVERT_TO_GENERATED:
            if state.override_text is None:
                raise ServiceError("invalid_transition", "This section has no edit to revert.")
            state.override_text = None
            state.override_review_revision = None
            kind = AuditEventType.NOTE_SECTION_REVERTED
        else:
            state.accepted_review_revision = e.review_revision
            state.accepted_by = self.clinician
            state.accepted_at = now
            kind = AuditEventType.NOTE_SECTION_ACCEPTED
        e.revision += 1
        e.updated_at = now
        event = self._event(e, kind, f"{key.value.replace('_', ' ').title()} note section updated.")
        self.store.save(e, [event], req.expected_revision)
        return build_view(e)

    def create_export(self, encounter_id: str, expected_revision: int):
        e = self.store.load(encounter_id)
        view = build_view(e)
        if e.revision != expected_revision:
            raise ServiceError(
                "revision_conflict", "This encounter changed elsewhere.", 409, {"current_revision": e.revision}
            )
        if not view.export.can_export:
            raise ServiceError(
                "export_blocked",
                "Export is blocked until every finding is reviewed.",
                409,
                {"blocked_reasons": [x.model_dump(mode="json") for x in view.export.blocked_reasons]},
            )
        now = self.clock.now()
        export_id = self.id_fn("exp")
        bundle, manifest, excluded = build_bundle(approved_facts(e), e.patient, e.context, e.id, export_id, now)
        export = FhirExport(
            id=export_id,
            generated_at=now,
            generated_by=self.clinician,
            review_revision=e.review_revision,
            bundle=bundle,
            manifest=manifest,
            excluded=excluded,
        )
        e.exports.append(export)
        e.revision += 1
        e.updated_at = now
        event = self._event(
            e,
            AuditEventType.EXPORT_GENERATED,
            "Generated FHIR R4 bundle.",
            payload={"resource_counts": resource_counts(bundle), "excluded_count": len(excluded)},
        )
        self.store.save(e, [event], expected_revision)
        return export
