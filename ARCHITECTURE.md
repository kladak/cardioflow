# CardioFlow — Architecture

> **AI proposes. Structured state validates. The clinician approves. Deterministic software acts.**

This document is authoritative. Where it and code disagree, the typed code in
`backend/app/domain/`, `backend/app/extraction/contract.py` and `backend/app/api/schemas.py`
wins for *shapes*; this document wins for *behavior*. Fix whichever is wrong in the same PR.

Companion docs: [PRODUCT_SPEC.md](PRODUCT_SPEC.md) (experience), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (order of work), [TEST_PLAN.md](TEST_PLAN.md) (verification).

---

## 1. Scope

CardioFlow demonstrates one workflow, excellently, next to an EHR:

```
Encounter → Extract → Review → Validate → Export
transcript   candidate   clinician   simulated     FHIR R4
             facts +     approves /  prior-auth    bundle of
             evidence    edits /     readiness     approved state
                         rejects
```

**It is not:** an EHR, an ambient scribe, a payer integration, a CDS system, a multi-tenant product,
or HIPAA-grade infrastructure. All data is synthetic. There is no authentication; a single demo
clinician identity comes from config.

## 2. System shape

One FastAPI process, one SQLite file, one Next.js app. No queues, no workers, no services.

```
┌──────────────────────────── Next.js (frontend/) ────────────────────────────┐
│  Encounter list  ·  Encounter workspace (transcript | review surface)       │
│  TanStack Query cache keyed by encounter id; every mutation returns the     │
│  full EncounterView, which replaces the cache entry.                        │
└───────────────────────────────▲─────────────────────────────────────────────┘
                                │ JSON over HTTP (types generated from OpenAPI)
┌───────────────────────────────┴──────────── FastAPI (backend/) ─────────────┐
│ api/        routes, error envelope, request→service mapping                  │
│ services/   encounter_service: the ONLY place that mutates an Encounter      │
│             view_builder: Encounter → EncounterView (derived state)          │
│ extraction/ provider (mock | anthropic) → pipeline (parse, validate,         │
│             ground, flag) → candidate Facts         ◄── AI BOUNDARY          │
│ review/     state machine for Fact review actions                            │
│ policy/     policy JSON + registered evaluators     ◄── deterministic        │
│ note/       note generator (approved facts → lines) ◄── deterministic        │
│ fhir/       mapper (approved facts → Bundle)        ◄── deterministic        │
│ store/      SQLite: encounters (JSON doc) + audit_events (append-only)       │
│ core/       settings, clock, id generation                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Repository layout (target)

```
cardioflow/
  ARCHITECTURE.md  PRODUCT_SPEC.md  IMPLEMENTATION_PLAN.md  TEST_PLAN.md  README.md  Makefile  .env.example
  backend/
    pyproject.toml
    app/
      main.py                      # FastAPI app factory: create_app(settings) -> FastAPI
      core/        settings.py clock.py ids.py
      domain/      facts.py encounter.py policy.py          # EXISTS — authoritative types
      api/         schemas.py (EXISTS) routes.py errors.py
      services/    encounter_service.py view_builder.py
      extraction/  contract.py prompt.py (EXIST) pipeline.py grounding.py flags.py numbers.py
                   providers/ base.py (EXISTS) mock.py anthropic.py
      review/      transitions.py
      policy/      policies/sim_ivabradine_hfref_v1.json (EXISTS) loader.py evaluators.py engine.py dates.py
      note/        generator.py labels.py
      fhir/        terminology.py (EXISTS) mapper.py
      store/       sqlite.py
    fixtures/
      encounters/  hfref_golden.json hfref_ambiguous.json            # EXIST
      extraction/  <fixture>.<scenario>.json|txt, expected_outcomes.json  # EXIST
    tests/ unit/ integration/
  frontend/        Next.js App Router app (created in Phase 0), design-tokens.css (EXISTS)
  e2e/             Playwright specs
```

### Stack decisions

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI, Python 3.11, Pydantic v2 | Required; Pydantic is also the validation engine for the LLM contract. |
| Persistence | SQLite via stdlib `sqlite3`; encounter aggregate stored as one JSON document | One aggregate, one writer, no joins needed. Zero ops. Survives restarts for demos. |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + TanStack Query | Required stack; Query handles loading/mutation state without a custom store. |
| API types in TS | `openapi-typescript` generated from FastAPI's `/openapi.json` | One source of truth for shapes. Never hand-write DTO types. |
| Unit/integration tests | pytest + FastAPI `TestClient` + temp SQLite | Fast, no network. |
| Frontend component tests | Vitest + React Testing Library | Only for the few interaction-heavy components. |
| E2E | Playwright (Chromium), backend in mock mode | Deterministic golden and adversarial paths. |
| Real LLM | Anthropic Messages API with a single forced tool | Optional; the app is fully functional without credentials. |

---

## 3. Domain model

Source of truth: `backend/app/domain/*.py`. Summary:

```
Encounter (aggregate, persisted)
├─ id, created_at, updated_at
├─ revision            bumps on every mutation (optimistic concurrency)
├─ review_revision     bumps only when APPROVED fact state changes (staleness driver)
├─ patient: SyntheticPatient        ← from fixture/request, NEVER from AI
├─ context: EncounterContext        ← date, specialty, clinician, visit type
├─ transcript: Transcript[TranscriptSegment{id "s7", seq, speaker, speaker_label, text}]
├─ extraction_runs: ExtractionRun[]  (status, attempts, issues[], accepted_fact_ids, raw_output)
├─ facts: Fact[]
│   ├─ id, fact_type, origin (extraction | clinician), extraction_run_id
│   ├─ candidate: CandidateFact | null   ← immutable AI proposal
│   │     value, assertion, evidence[EvidenceSpan], model_confidence, rationale, flags[]
│   ├─ review: ReviewState               ← pending | approved | rejected, who, when, reason
│   └─ approved: ApprovedFact | null     ← clinician-attested state (present iff approved)
│         value, assertion, evidence[], edited, attestation_note, approved_by, approved_at
├─ note_sections: NoteSectionState[]     ← only clinician overrides/acceptances; text is derived
├─ exports: FhirExport[]                 ← immutable snapshots
└─ last_requirement_statuses             ← for READINESS_CHANGED audit diffing only
AuditEvent (separate append-only table)
AuthorizationPolicy (static JSON, loaded at startup)
```

### 3.1 Candidate vs approved — the core separation

- `Fact.candidate` is written **once** at ingest and never mutated. It is what the AI said.
- `Fact.approved` is what the clinician attested. It is created by an approve action (copying the
  candidate value/assertion/evidence), or by an approve-with-edit action (request value/assertion,
  candidate evidence, `edited=true`), or at creation for clinician-origin facts.
- **Single read gate:** `services/encounter_service.approved_facts(encounter) -> list[ApprovedFactRef]`
  returns `(fact_id, fact_type, origin, approved)` tuples for facts with `review.status == approved`.
  The policy engine, note generator and FHIR mapper take **only** this list (plus `context`/`patient`).
  They must not import `CandidateFact` or access a `.candidate` attribute. Enforce with an AST-based unit test over
  these packages (TEST_PLAN U-GATE-1); the word "candidate" in user-facing strings is fine.
- Pending candidates are surfaced to downstream *views* only as ids (e.g. `pending_fact_ids` on a
  requirement, `pending_fact_count` on a note section) so the UI can link to them. They never affect
  a status, a note line, or a FHIR resource.

### 3.2 Fact catalog

Closed set (`FactType`). Each type has a strict value model (`VALUE_MODEL`), an allowed assertion set
(`ALLOWED_ASSERTIONS`), and cardinality (`SINGLE_VALUED_TYPES`).

| fact_type | value (key fields) | allowed assertions | cardinality | feeds |
|---|---|---|---|---|
| hf_diagnosis | hf_type, chronicity | affirmed, uncertain | single | R3, note A/P, Condition |
| lvef | percent, percent_upper?, measured_on_text?, modality | affirmed, uncertain | single | R4, note O, Observation |
| nyha_class | nyha, nyha_upper? | affirmed, uncertain | single | R5, note A/P, Observation |
| resting_heart_rate | bpm | affirmed, uncertain | single | R7, note O, Observation |
| blood_pressure | systolic, diastolic | affirmed, uncertain | single | R9, note O, Observation |
| cardiac_rhythm | rhythm, source | affirmed, uncertain | single | R6, note O, Observation |
| medication | drug, raw_name, dose_value?, dose_unit?, dose_text?, frequency, status, adherence_note? | affirmed, uncertain, hypothetical | multi | R1, R8, note Meds/A/P, MedicationStatement/Request |
| beta_blocker_dose_status | status | affirmed, uncertain | single | R8, note A/P (not exported) |
| condition_history | condition, timing_text? | affirmed, negated, uncertain | multi | R6, note S, Condition |
| symptom | symptom, detail_text? | affirmed, negated, uncertain | multi | note S (not exported) |

Single-valued invariant: at most one **approved** fact per single-valued type. Multiple *candidates*
may exist (flagged `conflicting_candidates` if their values differ). Approving a second one returns
`409 single_value_conflict` with `details.approved_fact_id`; the clinician must reject or reopen the
existing one first. No silent replacement.

---

## 4. Provenance model

Provenance is a chain of ids that survives every stage:

```
TranscriptSegment.id ──► EvidenceSpan{segment_id, char_start, char_end, quote, speaker}
                               │ (1..3 per candidate; copied into ApprovedFact)
                               ▼
                           Fact.id ──► NoteLine.fact_ids
                               │   ──► RequirementEvaluation.used_fact_ids / pending_fact_ids
                               │   ──► ExportManifestEntry.fact_ids  +  FHIR resource.identifier
                               │   ──► ExportExclusion.fact_id
                               └──────► AuditEvent.fact_id
```

- Offsets are computed **by the server**, never trusted from the model (§5.3).
- Invariant: `transcript.segment(span.segment_id).text[span.char_start:span.char_end] == span.quote`.
  Checked at ingest and re-asserted in a property test over every stored fact (TEST_PLAN U-PROV-*).
- Transcripts are immutable after creation, so spans can never drift.
- Clinician-origin facts have `evidence=[]` and a required `attestation_note` (e.g. "Per echo report
  2026-06-12 in EHR"). The UI labels them "Entered by clinician", never shows fake highlights.
- Edited facts keep the candidate's evidence (the evidence is still *where the clinician looked*),
  and `edited=true`; the UI shows "Edited — AI proposed: 25%".
- FHIR resources carry `identifier: [{system: "urn:cardioflow:fact", value: <fact_id>}]` and the export
  manifest maps resource → fact_ids, so a bundle entry can be traced back to transcript text.

---

## 5. The AI boundary: extraction

The LLM's entire authority: propose `(fact_type, value, assertion, evidence quotes, confidence, rationale)`.
It cannot create ids, offsets, statuses, flags, dates, codes, notes, rule outcomes or FHIR.

### 5.1 Provider abstraction

`app/extraction/providers/base.py` (exists). A provider returns raw text + model name, or raises
`ProviderError`. Selected by `CARDIOFLOW_EXTRACTION_PROVIDER=mock|anthropic`.

- **MockProvider**: returns `fixtures/extraction/{fixture_id}.{scenario}.json` (or `.txt`) verbatim.
  `scenario` = `CARDIOFLOW_MOCK_SCENARIO` (default `default`). Encounters not created from a fixture
  (pasted transcripts) get `{"schema_version": "cardioflow.extraction.v1", "facts": []}` → run
  `succeeded` with 0 facts → UI shows the "nothing extracted" state. No repair retry.
- **AnthropicProvider**: Messages API, `temperature=0`, one tool `record_extraction` with
  `input_schema = extraction_json_schema()`, `tool_choice={"type":"tool","name":"record_extraction"}`,
  60 s timeout, `CARDIOFLOW_ANTHROPIC_MODEL` **required** (no hardcoded model id). Transcript is sent as
  lines `[s12] CLINICIAN (Dr. Reyes): text` (see `prompt.py`). `raw_text = json.dumps(tool_input)`;
  if no tool_use block is returned, `raw_text` is the concatenated text content (will fail parsing).
  Pydantic emits `$defs`/`$ref` and a discriminator mapping; if the API rejects any schema keyword, add a small
  `inline_refs(schema)` helper in the provider that resolves `$ref`s and drops `discriminator` — the server-side
  validation is unchanged, so this only affects what the model is shown.

### 5.2 Pipeline (`extraction/pipeline.py`) — exact order

```
run_extraction(encounter, provider, clock, ids) -> (ExtractionRun, list[Fact])

attempt = 1
loop:
  try raw = provider.extract(req)                   except ProviderError → issue PROVIDER_ERROR → FAILED
  1. json.loads(raw.raw_text)                       fail → issue INVALID_JSON
  2. ExtractionEnvelope.model_validate(obj)         fail → issue ENVELOPE_INVALID
                                                     len(facts) > 60 → TOO_MANY_FACTS (envelope max_length)
  if step 1/2 failed and provider.supports_repair_retry and attempt == 1:
      attempt = 2; req.repair_hint = short summary of the error (≤ 1000 chars); continue
  if step 1/2 failed: → FAILED (issues from the last attempt only; raw_output = last raw text)
  break
for index, item in enumerate(envelope.facts):
  3. ITEM_ADAPTER.validate_python(item)             fail → ITEM_INVALID(item_index, errors[:5]); skip
  4. assertion_allowed(type, value, assertion)      fail → DISALLOWED_ASSERTION; skip  (facts.py; incl. hypothetical only for planned meds)
  5. ground each evidence ref (§5.3)                 per ref: UNKNOWN_SEGMENT | QUOTE_NOT_FOUND; drop ref
     if no refs survive                              → UNGROUNDED_FACT; skip
     dedupe identical spans (same segment+offsets)
  6. build CandidateFact(value, assertion, spans, confidence, rationale, flags=[])
accepted = all built candidates
  7. compute flags (§5.4) over accepted (needs the full set for CONFLICTING_CANDIDATES)
  8. Facts: id=fct_*, origin=extraction, review=pending, approved=None
status: FAILED if (1/2 failed) or (len(accepted)==0 and issues)
        SUCCEEDED_WITH_ISSUES if accepted and issues
        SUCCEEDED otherwise (including 0 facts, 0 issues)
```

Issues within one item are appended in the order they occur; the order of issues across items follows
item index. `expected_outcomes.json` relies on this order.

### 5.3 Grounding algorithm (`extraction/grounding.py`)

The model supplies `segment_id` + `quote`. The server finds the span.

1. Segment lookup by id. Missing → `UNKNOWN_SEGMENT`. **Do not search other segments** (a quote cited to
   the wrong place is treated as ungrounded; strictness is the hallucination defence).
2. Exact substring search (`text.find(quote)`), first occurrence.
3. Else normalized search: build `norm(text)` with an index map back to original offsets, where `norm` =
   casefold; `’ ‘ → '`; `“ ” → "`; `– — → -`; any run of whitespace → one space; strip. Search
   `norm(quote)` in `norm(text)`; map start/end back to original indices.
4. Not found → `QUOTE_NOT_FOUND`.
5. The stored `EvidenceSpan.quote` is **always** `text[char_start:char_end]` (original text), never the
   model's string.

No fuzzy matching beyond this. A paraphrase is not evidence.

### 5.4 Deterministic review flags (`extraction/flags.py`)

Computed once at ingest from candidate + transcript. Stored on `CandidateFact.flags`. Deterministic order =
enum declaration order.

| Flag | Rule |
|---|---|
| `model_low_confidence` | `model_confidence == low` |
| `value_not_in_evidence` | for fields in `NUMERIC_GROUNDING_FIELDS[type]` that are non-null: the number does not appear in **any** evidence quote. Numbers in quotes are found by `numbers.py`: digit tokens incl. decimals (`12.5`, `49/51` → 49 and 51), and English number words 0–199 incl. hyphenated (`twenty-five`). Compare as floats. |
| `hedged_language` | any evidence quote matches (case-insensitive, word-boundary, apostrophes normalized) one of: `maybe, i think, not sure, probably, about, around, like, might, possibly, or so, don't remember, i guess, roughly, approximately` |
| `patient_reported_measurement` | type ∈ `MEASUREMENT_TYPES` and every span's speaker is `patient` |
| `conflicting_candidates` | type ∈ `SINGLE_VALUED_TYPES` and another accepted candidate of the same type in this run has a different `value` |
| `uncertain_or_hypothetical` | assertion ∈ {uncertain, hypothetical} |
| `evidence_is_question` | every span's **segment text** ends with `?` (after rstrip) |

Flags never change value, assertion or status. They (a) sort flagged facts first in the review queue,
(b) render reasons in the UI, (c) are counted in `fact_counts.pending_flagged`.

Known limit, stated plainly: a grounded quote with a semantically wrong value that is not numeric
(e.g. `hf_type: hfpef` citing "reduced ejection fraction") is **not** caught by software. Clinician review is
the control. The UI therefore always shows the quote next to the value.

### 5.5 Absence is not a fact

- The contract has no "not documented" field. If nothing is said, the model emits nothing.
- Software computes absence: a requirement with no approved fact of its types is `MISSING`; a note
  section omits the line; FHIR emits no resource.
- "Denied" (negated) is a positive statement with evidence and is distinct from "not mentioned".
- Unstated fields inside a value are `null`/`unspecified`; unit, frequency, modality, chronicity are
  never defaulted. Rules treat `unspecified` as insufficient (REQUIRES_REVIEW), never as a pass.
- Dates are carried as spoken text; resolution is deterministic (§7.3). Unresolvable → REQUIRES_REVIEW.

### 5.6 Re-running extraction

`can_run = (no fact has review.status != pending) and (no clinician-origin facts)`. When allowed, a new
run **replaces** all existing (still-pending) extraction-origin facts; older runs stay in
`extraction_runs` for inspection. Once review has begun, extraction is locked (`409 extraction_not_allowed`).
Rationale: merging a new AI proposal into partially reviewed state creates ambiguous provenance for no
demo value.

---

## 6. Review state machine

`review/transitions.py`. Actions come from `ReviewFactRequest.action`.

```
                approve / approve_with_edit
   ┌─────────┐ ─────────────────────────────► ┌──────────┐
   │ PENDING │                                 │ APPROVED │ ◄─┐ approve_with_edit
   └─────────┘ ◄───────── reopen ───────────── └──────────┘ ──┘ (re-attest new value)
      │   ▲                                         │
reject│   │reopen                              reject│
      ▼   │                                         ▼
   ┌──────────┐ ◄───────────────────────────────────┘
   │ REJECTED │
   └──────────┘
```

| From | Action | To | Preconditions | Effects | review_revision |
|---|---|---|---|---|---|
| pending | approve | approved | origin=extraction; single-value slot free | approved = copy(candidate), edited=false | +1 |
| pending | approve_with_edit | approved | `value` valid for type; assertion allowed; slot free | approved = request value/assertion, candidate evidence, edited = differs from candidate | +1 |
| approved | approve_with_edit | approved | same | replace approved; edited recomputed vs candidate (clinician-origin: edited=false, evidence []) | +1 |
| pending | reject | rejected | `reason` optional for pending | approved=None | +0 (approved state unchanged) |
| approved | reject | rejected | — | approved=None | +1 |
| approved | reopen | pending | origin=extraction | approved=None | +1 |
| rejected | reopen | pending | origin=extraction | — | +0 |
| — | add (POST /facts) | approved | slot free; attestation_note | new clinician-origin fact | +1 |
| approved | reject (clinician-origin) | rejected | — | approved=None (fact kept for audit) | +1 |

Any other pair → `409 invalid_transition` (e.g. `approve` on approved, `reopen` on pending, `reopen` on clinician-origin).
`approve` (plain) on clinician-origin is invalid. Every mutation: `revision += 1`, `updated_at = now`, audit event.

### 6.1 Invalidation (what a change to approved facts does)

Everything downstream is either **live-derived** (recomputed on every read from approved facts) or a
**snapshot** (stored with the `review_revision` it was built from).

| Artifact | Kind | On review_revision change |
|---|---|---|
| Prior-auth evaluation | live-derived | Recomputed immediately; response contains the new result. If any requirement status changed vs `last_requirement_statuses`, write `prior_auth.readiness_changed` with the diff and update the stored map. |
| Note generated lines | live-derived | Recomputed. |
| Note override | snapshot (`override_review_revision`) | Kept verbatim; `override_stale=true`. UI: "Findings changed since you edited this section" + [View generated] [Revert to generated]. Never auto-discarded. |
| Note acceptance | snapshot (`accepted_review_revision`) | `acceptance_stale=true`; UI shows section as needing re-acceptance. |
| FHIR export | snapshot (`review_revision`) | Kept immutable; `is_stale=true`; stage drops out of EXPORTED; UI: "Export out of date — approved findings changed after it was generated". New export required. |
| Extraction | — | Unaffected (locked once review starts). |

Why prior auth is live but export is a snapshot: evaluation is a cheap pure function that the clinician
should see react as they review; export is the consequential action and must be an explicit,
attributable, reproducible artifact.

Rejecting a *pending* fact does not bump `review_revision` because no approved state changed; nothing goes stale.

### 6.2 Concurrency

All mutating requests carry `expected_revision`. Mismatch → `409 revision_conflict` with
`details.current_revision`. The UI refetches and shows a toast "This encounter changed — refreshed." Single-user
demo, but it makes stale-UI bugs impossible to hide.

---

## 7. Prior-authorization engine (simulated)

### 7.1 Framing

- One policy: `policy/policies/sim_ivabradine_hfref_v1.json`. `simulated: true` is a `Literal[True]`;
  a non-simulated policy cannot load. Payer is "Simulated Demonstration Plan". The disclaimer is shown
  in the UI wherever readiness is shown.
- The engine answers one question: **"Do the clinician-approved facts in this encounter document the
  simulated criteria?"** It does not predict approval, submit anything, or advise treatment.
- Policy = data (requirements + evaluator name + params). Logic = a small registry of Python functions.
  No DSL: nine readable functions beat an interpreter.

### 7.2 Evaluation contract

```python
evaluate(policy, approved: list[ApprovedFactRef], pending: list[(fact_id, fact_type)],
         context: EncounterContext, review_revision: int) -> PriorAuthEvaluation
```

Pure, no clock (encounter date comes from context), no I/O. `pending_fact_ids` on each result =
pending facts whose type ∈ `requirement.fact_types` (links only).

**General principles (apply to every evaluator, in this order):**

1. No approved fact that can answer → `MISSING` (`missing_fact_types` = requirement.fact_types that are absent).
2. An approved fact that affirmatively fails the criterion with `assertion == affirmed` → `NOT_MET`.
3. Any of these → `REQUIRES_REVIEW` (all applicable reasons listed in the explanation):
   assertion `uncertain`/`hypothetical`; a required value field is `unspecified`/null; a measurement
   whose evidence is exclusively patient speech (extraction-origin only); unresolvable date; a condition
   that the policy text does not decide.
4. Otherwise → `SATISFIED`.

An uncertain fact can never yield SATISFIED or NOT_MET. A patient-reported measurement can never yield SATISFIED or NOT_MET.

**Overall:** `NOT_MET` if any NOT_MET → else `INCOMPLETE` if any MISSING → else `NEEDS_REVIEW` if any REQUIRES_REVIEW → else `READY`.

### 7.3 Evaluators

| Req | Evaluator | Logic (after general principle 1) |
|---|---|---|
| R1 | `requested_medication(drug)` | Approved medication facts with `drug == param` and `status == planned`. None: if an approved *active* fact for the drug exists → REQUIRES_REVIEW ("already active; continuation is outside this policy"); else MISSING. Any planned+affirmed → SATISFIED. Else (uncertain/hypothetical) → REQUIRES_REVIEW. |
| R2 | `context_specialty(specialty)` | `context.specialty == param` → SATISFIED else NOT_MET. `context_fields_used=["context.specialty"]`. |
| R3 | `hf_diagnosis(hf_type, chronicity)` | hf_type ∉ {param, unspecified} → NOT_MET. chronicity == acute → NOT_MET. hf_type/chronicity unspecified, chronicity acute_on_chronic, or uncertain → REQUIRES_REVIEW. Else SATISFIED. |
| R4 | `lvef_at_most(max_percent, max_age_days)` | Resolve date (§7.4). NOT_MET if affirmed and not patient-only and (`percent > max` or resolved age > max_age_days). REQUIRES_REVIEW reasons: `percent_upper > max` (range straddles threshold), uncertain, patient-only evidence, date null/unresolvable, date after encounter. Else SATISFIED. |
| R5 | `nyha_in(allowed, review_if)` | classes = {nyha, nyha_upper}. Uncertain → REQUIRES_REVIEW. All ∈ allowed → SATISFIED. Any ∈ review_if, or mixed in/out (e.g. I–II) → REQUIRES_REVIEW. All ∉ allowed ∪ review_if (class I) → NOT_MET. |
| R6 | `sinus_rhythm(accepted_sources)` | rhythm fact none → MISSING. rhythm ∈ {atrial_fibrillation, atrial_flutter, paced} & affirmed → NOT_MET. rhythm `other` → REQUIRES_REVIEW. sinus: REQUIRES_REVIEW if uncertain, source ∉ accepted_sources, patient-only, or an approved condition_history of atrial_fibrillation/atrial_flutter with assertion affirmed/uncertain exists ("sinus today, AF history — confirm eligibility"). Negated AF history is fine. Else SATISFIED. used_fact_ids includes the AF history fact when it influenced the result. |
| R7 | `heart_rate_at_least(min_bpm)` | bpm < min & affirmed & not patient-only → NOT_MET. Uncertain / patient-only → REQUIRES_REVIEW. Else SATISFIED. |
| R8 | `beta_blocker_optimized()` | Status fact present: `below_max_tolerated_dose` & affirmed → NOT_MET; uncertain → REQUIRES_REVIEW; else SATISFIED. No status fact: an approved medication with `DRUG_CLASS == beta_blocker` and status active → REQUIRES_REVIEW ("on {drug}; maximum-tolerated dose not documented"); otherwise MISSING. |
| R9 | `blood_pressure_at_least(min_systolic, min_diastolic)` | below either & affirmed & not patient-only → NOT_MET. Uncertain / patient-only → REQUIRES_REVIEW. Else SATISFIED. |

Explanations are f-string templates in `evaluators.py`, e.g.
`"LVEF 30% (echocardiogram, 2026-06-12, 53 days before visit) is at or below 35%."`,
`"No approved NYHA class. 1 candidate awaits review."`,
`"LVEF is patient-reported and uncertain (20–25%). Policy requires a documented measurement."`
They are tested verbatim for the golden path (snapshot) so wording changes are deliberate.

### 7.4 Spoken date resolution (`policy/dates.py`)

`resolve_spoken_date(text: str | None, encounter_date: date) -> date | None`. Supported, case-insensitive:
`YYYY-MM-DD`; `M/D/YYYY`; `Month D[st|nd|rd|th][, YYYY]`; `Mon D[, YYYY]`. Month+day without year → the most
recent occurrence on or before `encounter_date`. Anything else (`"April"`, `"last spring"`, `"a few months ago"`) → `None`.
Resolved dates are displayed alongside the spoken text in the UI.

### 7.5 UI connection

Each `RequirementEvaluation` renders as a row: status · title · explanation · linked facts.
`used_fact_ids` render as chips (value summary). Clicking a chip selects the fact → transcript highlights its
evidence. `pending_fact_ids` render as "Review candidate →". `MISSING` rows with `fact_types` offer
"Add from chart" which opens the add-fact form pre-set to the first fact type. `R2` shows "From encounter
context". See PRODUCT_SPEC §5.4.

---

## 8. Note generation (deterministic)

The note is a **projection** of approved facts, not LLM prose. Decision rationale: generated clinical
narrative is where hallucination hides; the demo's value is showing that every sentence is traceable.
(An LLM "polish" pass constrained to cite fact ids is a possible later extension, out of scope.)

`note/generator.py`: `generate(approved, context) -> dict[NoteSectionKey, list[NoteLine]]`. Each line cites
the fact ids it was built from. Order within a section follows catalog order, then first evidence seq.
Suffixes: uncertain → ` (uncertain)`; patient-only measurement → ` (patient-reported)`.

| Section | Lines |
|---|---|
| Subjective | symptom affirmed: `Reports {label}{ — detail}.` · negated: `Denies {label}.` · uncertain: `Possible {label}{ — detail}.` · condition_history affirmed: `History of {label}{ ({timing})}.` · negated: `Denies prior diagnosis of {label}.` · uncertain: `Uncertain history of {label}{ ({timing})}.` |
| Objective | `BP {s}/{d} mmHg.` · `Resting HR {bpm} bpm.` · `Rhythm: {rhythm label} ({source}).` · `LVEF {p}%[–{u}%] ({modality}{, date}).` |
| Medications | status active/held/discontinued, one line each: `{Drug label}[ ({raw_name} if different)] {dose} {frequency}[ — {status if not active}][. Note: {adherence_note}].` dose = `{dose_value:g} {dose_unit}` if unit present, else `dose_text`, else omitted. Drug `other` uses raw_name. |
| Assessment & Plan | hf_diagnosis: `{Chronicity} {HF type label}[, LVEF {p}%][, NYHA class {n}].` (cites hf, lvef, nyha facts) · bb status: `Beta-blocker: {status label}.` · planned med affirmed: `Start {drug} {dose} {frequency}.` · uncertain: `Possible plan: {drug} {dose} {frequency}.` · hypothetical: `Consider {drug} in the future.` |

`effective_text` = override if present, else lines joined by `\n`. Empty section → `generated_lines=[]`,
the UI renders a placeholder that is **not** part of `effective_text`. "Copy note" copies the four sections'
`effective_text` with titles. That is the only note "export"; the note is not in the FHIR bundle (§9.4).

---

## 9. FHIR boundary

### 9.1 Principles

- Input: `approved_facts`, `patient`, `context`, `encounter.id`, `export_id`, `generated_at`. Output: Bundle dict +
  manifest + exclusions. Pure function in `fhir/mapper.py`.
- No model output, candidate state, note text, or policy result enters the bundle.
- Deterministic: resource ids are `uuid5(NAMESPACE, f"{encounter_id}:{fact_id or 'patient'|'encounter'}")`,
  entries ordered Patient, Encounter, Condition*, Observation*, MedicationStatement*, MedicationRequest*
  (within type: catalog order, then fact id). Same approved state ⇒ byte-identical bundle except
  `Bundle.timestamp` and `Bundle.id`.
- Bundle `type: collection`, `fullUrl: urn:uuid:<id>`, references by `urn:uuid:`.
- Every fact-derived resource: `identifier=[{"system":"urn:cardioflow:fact","value":fact_id}]`,
  `subject → Patient`, `encounter → Encounter` (where the element exists).

### 9.2 Resource mapping

| Approved fact | Resource | Key elements |
|---|---|---|
| (patient) | Patient | identifier `urn:cardioflow:synthetic-mrn`; name; gender; birthDate; `meta.tag` `{system:"urn:cardioflow", code:"synthetic"}` |
| (context) | Encounter | status `finished`; class `http://terminology.hl7.org/CodeSystem/v3-ActCode#AMB`; type.text = visit_type; serviceType.text "Cardiology"; period.start = encounter_date; participant[0].individual.display = clinician_display (no Practitioner resource) |
| hf_diagnosis | Condition | category `encounter-diagnosis`; clinicalStatus `active`; verificationStatus affirmed→`confirmed`, uncertain→`provisional`; code: text "{Chronic} heart failure with reduced ejection fraction" + codings `cond.hfref`, and `cond.hf_chronic_systolic.icd10` only when hfref+chronic (verified codes only) |
| condition_history | Condition | no category; verificationStatus affirmed→`confirmed`, negated→`refuted`, uncertain→`unconfirmed`; no clinicalStatus; code text + verified coding; note[0].text = timing_text |
| lvef | Observation | status affirmed→`final`, uncertain→`preliminary`; category `imaging`; code `obs.lvef`; valueQuantity `{value, unit:"%", system:UCUM, code:"%"}` or valueRange low/high for ranges; effectiveDateTime = resolved date if any; method.text = modality |
| resting_heart_rate | Observation | category `vital-signs`; code `obs.heart_rate`; valueQuantity `/min`; effectiveDateTime = encounter_date |
| blood_pressure | Observation | category `vital-signs`; code `obs.bp_panel`; component systolic/diastolic `mm[Hg]` |
| nyha_class | Observation | category `exam`; code `obs.nyha`; valueCodeableConcept.text "NYHA class III" (or "II–III") |
| cardiac_rhythm | Observation | category `procedure` if source ecg/monitor else `exam`; code `obs.ecg_impression`; valueCodeableConcept text + `finding.sinus_rhythm` / `cond.atrial_fibrillation` coding when verified |
| medication status active/held/discontinued | MedicationStatement | status active/on-hold/stopped; medicationCodeableConcept.text = drug label (raw_name); dosage[0].text = "{dose} {frequency}"; note = adherence_note; assertion uncertain → status `unknown` |
| medication planned, affirmed | MedicationRequest | status `draft`; intent `plan`; dosageInstruction[0].text; requester.display = clinician |
| medication planned, uncertain | MedicationRequest | status `draft`; intent `proposal` |
| medication hypothetical | — excluded ("hypothetical medication is not exported") |
| symptom, beta_blocker_dose_status | — excluded ("not mapped in v1; represented in the clinical note") |

(`condition_history` deliberately has no category and no clinicalStatus: a transcript cannot establish whether a history item is active.)

Observation/Condition/MedicationRequest `category`, `status`, `verificationStatus` use FHIR-defined
code systems (`http://terminology.hl7.org/CodeSystem/observation-category`, `condition-clinical`,
`condition-ver-status`, `condition-category`), which are safe to emit.

### 9.3 External terminologies

`fhir/terminology.py` holds candidate LOINC/SNOMED CT/ICD-10-CM codes, all `status="unverified"`. The mapper
emits a `coding` **only if verified**; otherwise `CodeableConcept.text` only. Phase 6 includes verifying the
table against LOINC search, the SNOMED CT browser and CMS ICD-10-CM, and flipping `status` with a date.
RxNorm is intentionally empty until codes are looked up in RxNav; medications are text-only until then.
The FHIR inspector shows a "text-only concept" marker so the simplification is visible, not hidden.

### 9.4 Documented simplifications

- No profile conformance claimed (no US Core, no vitals profile); base R4 resources only.
- No Practitioner/Organization resources; displays only.
- Clinical note not exported (a Composition/DocumentReference is a reasonable next step).
- Prior-auth evaluation not exported (Da Vinci PAS/CRD/DTR are out of scope).
- No FHIR Provenance resource; traceability is via `identifier` + export manifest.
- Validation in tests uses `fhir.resources` R4B models (R4B is structurally identical to R4 for the
  resources and elements used here). Tests also assert `resourceType` and required elements explicitly.

### 9.5 Export gate

`can_export` iff `pending == 0` and `approved ≥ 1`. Blocked reasons: `pending_facts` (with ids), `no_approved_facts`.
Prior-auth readiness is **not** a gate (documentation export is independent of payer criteria) and note acceptance is
**not** a gate (note is not exported). `POST /exports` when blocked → `409 export_blocked` + `export.blocked` audit event.

---

## 10. API

Base `/api`. JSON only. All mutations take `expected_revision` and return the full `EncounterView` (except export
creation, which returns `ExportDetail`). Shapes in `app/api/schemas.py`.

| Method & path | Body | 2xx | Errors |
|---|---|---|---|
| GET `/api/health` | — | `{"status":"ok","provider":"mock"}` | — |
| GET `/api/fixtures` | — | `FixtureListItem[]` | — |
| GET `/api/policies/{policy_id}` | — | `PolicyView` | 404 not_found |
| POST `/api/encounters` | `CreateEncounterRequest` | 201 `EncounterView` | 404 unknown_fixture · 422 validation_error · 422 transcript_parse_error |
| GET `/api/encounters` | — | `EncounterListItem[]` (updated_at desc) | — |
| GET `/api/encounters/{id}` | — | `EncounterView` | 404 |
| POST `/api/encounters/{id}/extraction-runs` | `RunExtractionRequest` | 200 `EncounterView` (**also for FAILED runs**) | 404 · 409 revision_conflict · 409 extraction_not_allowed |
| POST `/api/encounters/{id}/facts/{fact_id}/review` | `ReviewFactRequest` | 200 `EncounterView` | 404 · 409 revision_conflict · 409 invalid_transition · 409 single_value_conflict · 422 validation_error (bad edit value / missing value) |
| POST `/api/encounters/{id}/facts` | `AddFactRequest` | 201 `EncounterView` | 404 · 409 revision_conflict · 409 single_value_conflict · 422 |
| POST `/api/encounters/{id}/note-sections/{key}` | `NoteSectionRequest` | 200 `EncounterView` | 404 · 409 revision_conflict · 409 invalid_transition (revert when not overridden) · 422 (edit without text) |
| POST `/api/encounters/{id}/exports` | `CreateExportRequest` | 201 `ExportDetail` | 404 · 409 revision_conflict · 409 export_blocked |
| GET `/api/encounters/{id}/exports/{export_id}` | — | `ExportDetail` (is_stale computed) | 404 |
| GET `/api/encounters/{id}/audit` | — | `AuditEvent[]` (seq asc) | 404 |

Notes:
- Model-output failure is a **domain outcome** (run FAILED, recorded, audited) → HTTP 200. HTTP errors are reserved for client mistakes and state conflicts. Unhandled exceptions → 500 `{"error":{"code":"internal_error"}}` without stack traces.
- Pydantic request validation errors are re-wrapped into the error envelope with `details.errors`.
- Transcript paste format: each non-blank line `ROLE: text` where ROLE ∈ `CLINICIAN|PATIENT|STAFF|OTHER`
  (case-insensitive). `speaker_label` = role title-cased. Any other line → 422 `transcript_parse_error` with `details.line`.
- Why `POST …/review` with an action instead of `PATCH …/facts/{id}`: the operations are state-machine
  transitions with different preconditions and audit semantics, not partial updates.
- No separate "evaluate prior auth" endpoint: evaluation is derived and present in `EncounterView.prior_auth` (nullable only until Phase 4 lands; see schema comment).
- CORS: allow `http://localhost:3000` only (config).

---

## 11. Persistence

`store/sqlite.py`. File `backend/data/cardioflow.db` (gitignored); tests use `tmp_path`.

```sql
CREATE TABLE IF NOT EXISTS encounters (
  id TEXT PRIMARY KEY, revision INTEGER NOT NULL, doc TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, encounter_id TEXT NOT NULL REFERENCES encounters(id),
  seq INTEGER NOT NULL, at TEXT NOT NULL, type TEXT NOT NULL, doc TEXT NOT NULL,
  UNIQUE (encounter_id, seq));
```

- `save(encounter, events, expected_revision)` runs in one transaction:
  `UPDATE encounters SET … WHERE id=? AND revision=?`; rowcount 0 → `RevisionConflict`. Then inserts events.
- Load = `Encounter.model_validate_json(doc)`, so every read re-checks invariants.
- One connection per request (`check_same_thread=False` not needed); WAL mode on.
- No migrations tooling: schema is created at startup; `make reset-db` deletes the file.

## 12. Audit

Lightweight, append-only, human-readable. Types in `AuditEventType`. Written by `encounter_service` in the same
transaction as the change. Each has a one-sentence `summary` and a small `payload`:

| Event | Actor | payload |
|---|---|---|
| encounter.created | clinician | fixture_id, segment_count |
| extraction.completed / failed | system (`extraction:{provider}`) | run_id, status, attempts, accepted_count, issue_counts_by_kind, model |
| fact.approved | clinician | fact_type, value |
| fact.edited | clinician | fact_type, before (candidate or previous approved), after, assertion_before/after |
| fact.rejected | clinician | fact_type, reason, was_approved |
| fact.reopened | clinician | fact_type, previous_status |
| fact.added | clinician | fact_type, value, attestation_note |
| note.section_edited / reverted / accepted | clinician | key, review_revision |
| prior_auth.readiness_changed | system | overall_before, overall_after, changes: [{requirement_id, from, to}], review_revision |
| export.generated | clinician | export_id, review_revision, resource_counts, excluded_count |
| export.blocked | clinician | blocked_reasons |

No read events, no field-level diffs of the whole aggregate, no hash chains.

## 13. Configuration (`core/settings.py`, pydantic-settings, prefix `CARDIOFLOW_`)

| Var | Default | Notes |
|---|---|---|
| `CARDIOFLOW_DB_PATH` | `backend/data/cardioflow.db` | |
| `CARDIOFLOW_EXTRACTION_PROVIDER` | `mock` | `mock` \| `anthropic` |
| `CARDIOFLOW_MOCK_SCENARIO` | `default` | E2E/test override |
| `CARDIOFLOW_ANTHROPIC_MODEL` | — | required when provider=anthropic; startup error otherwise |
| `ANTHROPIC_API_KEY` | — | required when provider=anthropic |
| `CARDIOFLOW_DEMO_CLINICIAN` | `Dr. A. Reyes` | actor for all clinician actions |
| `CARDIOFLOW_CORS_ORIGINS` | `http://localhost:3000` | |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | frontend |

`core/clock.py` (`Clock` protocol, `SystemClock`, `FixedClock`) and `core/ids.py` (`new_id(prefix)` → `prefix_` + 12 lowercase base32 chars; `SequentialIds` for tests) are injected via FastAPI dependencies so tests are deterministic.

## 14. Decision log

| # | Decision | Alternatives rejected | Reason |
|---|---|---|---|
| D1 | Modular monolith, SQLite JSON aggregate | Postgres + ORM; event sourcing | One aggregate, one user; invariants re-validated on load. |
| D2 | Model returns quotes; server computes offsets | Model returns offsets | LLMs miscount characters; server grounding doubles as hallucination check. |
| D3 | Two-level validation (envelope strict, items individually) | All-or-nothing | One bad item should not discard 17 good ones; the dropped item is still visible as an issue. |
| D4 | Candidate and approved state are separate fields on one Fact | Separate tables / copying into a new entity | Keeps provenance and "what AI said vs. what clinician attested" side by side for the UI. |
| D5 | Prior-auth evaluation live-derived; export is a snapshot | Explicit "Evaluate" button; auto-export | Readiness should react during review; export is the consequential act. |
| D6 | Named evaluator functions + JSON params | Rule DSL / JSON-logic | Nine functions are more readable, testable, and explainable. |
| D7 | Deterministic note from approved facts | LLM-generated narrative | Every sentence traceable; no second hallucination surface. |
| D8 | Unverified codes emitted as text only | Emit best-guess codes | Wrong codes are worse than no codes. |
| D9 | Synchronous extraction request | Background job + polling | Mock is instant; real call ≤ 60 s with a loading state. Add a job only if it hurts. |
| D10 | Single-valued conflicts are 409s, not auto-replace | Last approve wins | Silent replacement of an attested value is unsafe. |
| D11 | Extraction locked once review begins | Merge re-runs | Merge semantics would muddle provenance for no demo value. |
| D12 | No auth; demo clinician from config | Fake login screen | Avoid fake controls. |
