# CardioFlow architecture

This document describes the code in this repository. It does not describe a future production system.

## System boundary

```text
Browser
  -> Next.js interface
  -> same-origin /api rewrite
  -> FastAPI routes and application service
  -> typed encounter aggregate in SQLite

Synthetic transcript
  -> deterministic fixture provider
  -> strict extraction contract
  -> grounded candidate findings
  -> clinician review
  -> approved state
       -> note projection
       -> HFrEF documentation checks (applicable fixtures only)
       -> FHIR R4 bundle + explicit exclusions
```

Next.js serves the user interface and rewrites `/api/:path*` to the configured IPv4 backend origin. FastAPI owns API validation, state transitions, persistence, deterministic projections, and exports. OpenAPI types are generated into the frontend with `make gen-api`.

There is no external model, evidence-search service, payer connection, authentication layer, or deployment infrastructure in this prototype.

## Domain and state model

An `Encounter` is stored as one Pydantic-validated JSON aggregate. It contains fixture context, transcript segments, extraction runs, facts, note interaction state, exports, and the last HFrEF requirement statuses.

A fact has two distinct state areas:

- `candidate`: immutable provider proposal with assertion, exact evidence spans, confidence, and review flags.
- `approved`: clinician-reviewed value, assertion, copied provenance, reviewer, timestamp, and edited marker.

`review.status` is `pending`, `approved`, or `rejected`. Domain validation enforces that approved data exists if and only if the status is approved. Review actions use optimistic revision checks. Reopening removes approved state and returns an extraction-origin finding to pending.

`review_revision` changes only when approved fact state changes. It drives note acceptance and export staleness. General `revision` changes on every mutation and prevents lost updates.

## Extraction and provenance

The only configured provider is `MockProvider`. It returns versioned JSON fixtures for `hfref_golden`, `hfref_ambiguous`, and `gerd_simulated`. The same provider protocol could be implemented elsewhere, but no live provider exists here.

The extraction pipeline:

1. parses a strict versioned envelope;
2. validates each typed fact value and assertion;
3. checks segment identifiers, character offsets, and verbatim quotes;
4. drops ungrounded or invalid items;
5. adds deterministic review flags for ambiguity, conflict, recalled measurements, questions, and low confidence;
6. writes candidate findings only.

Contract failure is stored as a failed extraction run with domain-level issues; it does not produce partial authoritative state or break the encounter screen.

## Reviewed-state consumers

`approved_facts()` is the common boundary for downstream behavior.

- **Note generator:** deterministic section lines from approved facts. Pending counts are shown separately. Clinician overrides and acceptance revisions persist, with stale markers after reviewed state changes.
- **Documentation-readiness engine:** runs only for the HFrEF fixtures. It evaluates the versioned local policy against approved facts plus encounter context. Pending IDs may be reported as work to review but never satisfy a rule. GERD returns no HFrEF policy or evaluation and emits no readiness events.
- **FHIR mapper:** creates a collection Bundle from approved facts, synthetic Patient and Encounter context, and explicit exclusions. Rejected and proposed findings never enter the mapper.

## Policy provenance

`backend/app/policy/policies/sim_ivabradine_hfref_v1.json` is structured configuration, not a payer policy. Every requirement includes an evaluator, parameters, display threshold, provenance classification, explanatory note, source metadata, and verification date.

The interface separates patient evidence from criterion provenance. Application-specific checks are labelled as demonstration rules even when a cited source provides historical or contextual background. In particular, the retained 90/50 mmHg BP threshold is classified as a demo rule because the current label no longer states that exact number.

## FHIR mapping

The bundle always contains synthetic Patient and Encounter resources. Supported approved facts may add Condition, Observation, MedicationStatement, or MedicationRequest resources. Bundle references use deterministic `urn:uuid` identifiers. LVEF ranges use `valueRange`; uncertain history uses an unconfirmed verification status; spoken timing is preserved in a note; and structured medication dose units are retained.

The mapper intentionally uses text-only clinical concepts because the repository does not maintain externally verified terminology codes. Approved but unmapped facts are returned in `excluded` with a reason. `fhir.resources` validates the generated R4B structure in tests, which is not interoperability certification.

## Persistence and audit

`SQLiteStore` creates two tables:

- `encounters`: current aggregate JSON plus revisions and timestamps.
- `audit_events`: immutable event JSON with a unique `(encounter_id, seq)` order.

Encounter creation and updates write their audit events in the same SQLite transaction. Database triggers reject direct updates or deletes to `audit_events`; application code only inserts. Fixture runs create new encounters and do not reset existing data unless the operator explicitly runs `make reset-db`.

The database is ignored by Git. It contains synthetic demo state only.

## HTTP surface

The API provides health, fixture and policy reads; encounter create/list/read; extraction; fact review; note-section actions; export create/read; and audit reads. Every successful encounter mutation returns the full derived `EncounterView`, allowing the frontend to replace its local view atomically.

Errors use a stable envelope: `{"error":{"code":...,"message":...,"details":...}}`. Invalid extraction content is a recorded domain outcome with HTTP 200, while invalid requests, missing resources, and revision conflicts use HTTP status errors.

## Local runtime

Default ports are frontend `3000` and backend IPv4 `127.0.0.1:8010`. The explicit IPv4 origin avoids ambiguous `localhost` resolution. `scripts/check_port.py` fails clearly before backend startup if the API port is occupied.

Configuration is intentionally small:

- `CARDIOFLOW_DB_PATH` — SQLite path, default `data/cardioflow.db` relative to the backend process.
- `CARDIOFLOW_MOCK_SCENARIO` — fixture output variant, default `default`; tests use `invalid_json`.
- `CARDIOFLOW_DEMO_CLINICIAN` — synthetic reviewer display name.
- `CARDIOFLOW_CORS_ORIGINS` — direct API development origins.
- `CARDIOFLOW_API_ORIGIN` — Next.js rewrite target, default `http://127.0.0.1:8010` through the Makefile.

## Explicit production limitations

This local prototype lacks identity, access control, tenant isolation, encryption/key management, production database migration tooling, backups, monitoring, rate limiting, threat modeling, deployment configuration, clinical validation, payer integration, and certified FHIR interoperability. Those omissions are not hidden behind architecture diagrams or future-component names.
