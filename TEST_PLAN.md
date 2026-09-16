# CardioFlow — Test Plan

Levels: **U** = unit (pure functions, no I/O) · **I** = integration (FastAPI `TestClient`, temp SQLite, mock provider,
`FixedClock`, `SequentialIds`) · **C** = frontend component (Vitest + RTL) · **E** = end-to-end (Playwright, real
backend in mock mode, real Next dev/build server).

Single sources of expected values: `backend/fixtures/extraction/expected_outcomes.json` (pipeline + rules) and
golden snapshots under `backend/tests/snapshots/` (FHIR bundle, explanations, note text). Tests must read expectations
from these files rather than duplicating literals.

Each test id below should appear in the test name or docstring (e.g. `def test_U_GRD_2_normalized_match()`), so
coverage of this plan is greppable: `grep -rhoE "[UICE]-[A-Z]+-[0-9]+" backend/tests frontend/src e2e | sort -u`.

## 0. Already in the repo

`backend/tests/unit/test_contracts.py` — fixtures parse, default mock outputs are schema-valid and verbatim, malformed
fixtures fail at the intended level, policy is simulated, JSON schema publishes. Keep green forever.

## 1. Extraction contract & pipeline

| ID | Lvl | Case | Input | Expected |
|---|---|---|---|---|
| U-EXT-1 | U | Valid extraction | golden `default` | run `succeeded`; accepted counts = expected_outcomes; all facts `pending`; `candidate` set, `approved` null |
| U-EXT-2 | U | Invalid JSON | golden `invalid_json` | run `failed`; issues `[invalid_json]`; 0 facts; `raw_output` stored |
| U-EXT-3 | U | Envelope invalid | golden `envelope_invalid` | `failed`; `[envelope_invalid]` |
| U-EXT-4 | U | Item-level errors don't sink the run | golden `item_errors` | `succeeded_with_issues`; 1 lvef; issues in order `item_invalid×3, disallowed_assertion` with `item_index` 1,2,3,4 |
| U-EXT-5 | U | Too many facts | generated envelope with 61 items | `failed`; `envelope_invalid` (max_length) |
| U-EXT-6 | U | Provider error | fake provider raising `ProviderError` | `failed`; `[provider_error]`; message recorded |
| U-EXT-7 | U | Repair retry (real-provider path) | fake provider: attempt1 invalid JSON, attempt2 golden default; `supports_repair_retry=True` | `succeeded`; `attempts=2`; `repair_hint` non-empty on 2nd request; issues only from attempt 2 (none) |
| U-EXT-8 | U | No retry for mock | mock `invalid_json` | `attempts=1` |
| U-EXT-9 | U | Zero facts, zero issues | `{"schema_version":…, "facts": []}` | `succeeded`; stage later `transcript_ready` |
| U-EXT-10 | U | Unknown fixture → empty mock output | pasted transcript encounter | `succeeded`, 0 facts |
| U-EXT-11 | U | Extra top-level keys rejected | envelope + `"notes": "…"` | `failed`; `envelope_invalid` |
| U-EXT-12 | U | Model-supplied ids/offsets/status rejected | item with `"id"`, `"char_start"`, `"status"` | item `item_invalid` |
| U-EXT-13 | U | JSON schema is tool-compatible | `extraction_json_schema()` | serializes; every fact variant present in `oneOf`/`anyOf`; `additionalProperties: false` on items and values |

## 2. Grounding & provenance

| ID | Lvl | Case | Expected |
|---|---|---|---|
| U-GRD-1 | U | Exact match | span offsets such that `text[start:end] == quote` |
| U-GRD-2 | U | Case/whitespace-normalized match (`hallucinated` BP) | span `s7[15:41]`; stored quote = original `"Blood pressure 112 over 70"` |
| U-GRD-3 | U | Curly quotes / en-dash normalization | `I’d` in quote vs `I'd` in text matches; offsets map correctly |
| U-GRD-4 | U | Quote in a different segment than cited | `quote_not_found`; **not** re-anchored |
| U-GRD-5 | U | Unknown segment | `unknown_segment` |
| U-GRD-6 | U | Paraphrase | `quote_not_found` |
| U-GRD-7 | U | Partial evidence survives | BP keeps 1 span, 1 `quote_not_found` issue, fact accepted |
| U-GRD-8 | U | All evidence dropped | `ungrounded_fact`; fact not created |
| U-GRD-9 | U | Duplicate refs deduped | same quote twice → 1 span |
| U-PROV-1 | U | Span invariant property | for every fact in golden + ambiguous + hallucinated runs: `segment.text[s:e] == quote` and `speaker == segment.speaker` |
| U-PROV-2 | U | `EvidenceSpan` model rejects inconsistent length | `char_end-char_start != len(quote)` → ValidationError |
| I-PROV-1 | I | Provenance survives approval | approve LVEF → `approved.evidence == candidate.evidence` |
| I-PROV-2 | I | Provenance survives edit | edit LVEF → evidence unchanged, `edited=true` |
| I-PROV-3 | I | Provenance to FHIR | every non-Patient/Encounter bundle entry has `identifier[urn:cardioflow:fact]` ∈ approved fact ids; manifest fact_ids match |
| I-PROV-4 | I | Requirement → fact links | golden approve-all: every SATISFIED fact-based requirement has ≥1 `used_fact_ids`, each approved |

## 3. Flags & hallucination resistance

| ID | Lvl | Case | Expected |
|---|---|---|---|
| U-FLG-1 | U | Golden flags | exactly as `expected_outcomes.hfref_golden.default.flags` (only dizziness flagged) |
| U-FLG-2 | U | Ambiguous flags | exactly as expected_outcomes |
| U-FLG-3 | U | `value_not_in_evidence` | hallucinated HR 72 citing "heart rate 78 sitting" |
| U-FLG-4 | U | Number words | "twenty", "twenty-five", "one hundred twelve" → 20, 25, 112; "12.5" → 12.5; "49/51" → 49, 51 |
| U-FLG-5 | U | `evidence_is_question` | hallucinated AF citing only s20 |
| U-FLG-6 | U | `conflicting_candidates` | two LVEF items (30, 35) both grounded → both flagged; two identical LVEF values → not flagged |
| U-FLG-7 | U | Hedge lexicon word boundaries | "likely" does not match `like`; "about" matches; "don’t remember" (curly) matches |
| U-HAL-1 | U | Ambiguous: forbidden types absent | no nyha_class, cardiac_rhythm, hf_diagnosis, beta_blocker_dose_status facts |
| U-HAL-2 | U | Unstated unit stays null | golden furosemide `dose_unit is None`; ambiguous carvedilol `dose_unit is None` |
| U-HAL-3 | U | Rules never pass on `unspecified` | hf_diagnosis `{unspecified, unspecified}` approved → R3 REQUIRES_REVIEW |
| U-HAL-4 | U | Note never renders absent data | ambiguous approve-all note: no "NYHA", no "Rhythm", no "mg" for carvedilol |
| U-HAL-5 | U | FHIR never renders absent data | ambiguous approve-all bundle: no NYHA/rhythm Observation; carvedilol dosage text `"12.5"` without unit; no `effectiveDateTime` on LVEF |
| U-GATE-1 | U | Downstream reads approved only | AST scan of `policy/`, `note/`, `fhir/`: no import of `CandidateFact`, no `.candidate` attribute access, no `"candidate"` subscript |
| U-GATE-2 | U | Pending facts don't influence outputs | golden, nothing approved: evaluation = expected `requirements_with_nothing_approved`; note lines empty; mapper given approved=[] yields Patient+Encounter only |

## 4. Review state machine

| ID | Lvl | Case | Expected |
|---|---|---|---|
| U-REV-1 | U | Transition table | every (status, action, origin) pair in ARCHITECTURE §6: allowed → new state; otherwise `InvalidTransition` |
| U-REV-2 | U | review_revision deltas | per table (+1 / +0) including pending→rejected = +0 and rejected→reopen = +0 |
| U-REV-3 | U | `edited` computation | approve_with_edit with value equal to candidate → `edited=false` |
| U-REV-5 | U | Hypothetical only for planned meds | approve_with_edit medication status active + hypothetical → error; pipeline item same → `disallowed_assertion` |
| U-REV-4 | U | Edit validation | `{"bpm": "fast"}`, `{"bpm": 300}`, missing value → ValidationError; disallowed assertion (negated LVEF) → error |
| I-REV-1 | I | Approve | 200; fact approved; `revision+1`; `review_revision+1`; audit `fact.approved` |
| I-REV-2 | I | Edit | 200; audit `fact.edited` payload before/after |
| I-REV-3 | I | Reject pending with reason | 200; `review_revision` unchanged; audit `fact.rejected` with reason |
| I-REV-4 | I | Reject approved | `review_revision+1`; readiness recomputed |
| I-REV-5 | I | Reopen | approved → pending; audit `fact.reopened` |
| I-REV-6 | I | Invalid transition | approve on approved → 409 `invalid_transition` |
| I-REV-7 | I | Single-value conflict | add clinician LVEF while candidate LVEF approved → 409 `single_value_conflict` with `approved_fact_id` |
| I-REV-8 | I | Revision conflict | stale `expected_revision` → 409 `revision_conflict`, `details.current_revision`, no state change, no audit |
| I-REV-9 | I | Add clinician fact | 201; origin clinician; evidence []; attestation stored; audit `fact.added` |
| I-REV-10 | I | Clinician fact cannot be reopened | 409 |
| I-REV-11 | I | Extraction locked after review starts | approve one fact → POST extraction-runs → 409 `extraction_not_allowed` |
| I-REV-12 | I | Re-run before review replaces pending facts | run twice → fact count unchanged, ids differ, 2 runs listed |
| I-REV-13 | I | Aggregate invariant on load | tamper DB doc with two approved LVEFs → load raises; API 500 with `internal_error` (not silently served) |

## 5. Rule engine

| ID | Lvl | Case | Expected |
|---|---|---|---|
| U-RUL-1 | U | Golden approve-all | all SATISFIED; READY |
| U-RUL-2 | U | Golden nothing approved | expected `requirements_with_nothing_approved`; pending_fact_ids populated for R1, R3–R9 |
| U-RUL-3 | U | Ambiguous approve-all | expected statuses; INCOMPLETE |
| U-RUL-4 | U | Reevaluation scenarios | each entry of `reevaluation_scenarios` applied to golden approve-all |
| U-RUL-5 | U | Ambiguous resolution scenario | add AF rhythm → R6 NOT_MET, overall NOT_MET |
| U-RUL-6 | U | Overall precedence | table over status multisets: any NOT_MET > any MISSING > any REQUIRES_REVIEW > READY |
| U-RUL-7 | U | Uncertain never decides | for each evaluator: uncertain fact that would pass → REQUIRES_REVIEW; that would fail → REQUIRES_REVIEW |
| U-RUL-8 | U | Patient-only measurement never decides | LVEF/HR/BP/rhythm with patient-only evidence → REQUIRES_REVIEW; same value clinician-origin → decides |
| U-RUL-9 | U | Boundaries | LVEF 35 SAT / 36 NOT_MET; range 30–40 REQUIRES_REVIEW; range 36–40 NOT_MET; HR 70 SAT / 69 NOT_MET; BP 90/50 SAT, 89/60 NOT_MET, 100/49 NOT_MET; LVEF age 365 SAT / 366 NOT_MET; future date REQUIRES_REVIEW |
| U-RUL-10 | U | NYHA | I NOT_MET; II, III, II–III SAT; III–IV REQUIRES_REVIEW; IV REQUIRES_REVIEW; I–II REQUIRES_REVIEW |
| U-RUL-11 | U | Rhythm | AF affirmed NOT_MET; flutter NOT_MET; paced NOT_MET; other REQUIRES_REVIEW; sinus+source exam REQUIRES_REVIEW; sinus+AF history uncertain REQUIRES_REVIEW (AF fact in used_fact_ids); sinus+AF history negated SAT |
| U-RUL-12 | U | Beta-blocker | status below_max NOT_MET; contraindicated SAT; no status + carvedilol active REQUIRES_REVIEW; no status + no BB MISSING; no status + bisoprolol *discontinued* MISSING |
| U-RUL-13 | U | Requested med | planned affirmed SAT; hypothetical REQUIRES_REVIEW; only active ivabradine REQUIRES_REVIEW; none MISSING |
| U-RUL-14 | U | HF diagnosis | hfpef NOT_MET; acute NOT_MET; acute_on_chronic REQUIRES_REVIEW; unspecified REQUIRES_REVIEW |
| U-RUL-15 | U | Explanations snapshot | golden approve-all explanations match snapshot; ambiguous approve-all explanations match snapshot |
| U-RUL-16 | U | Purity | `evaluate` twice on same input → equal; no clock access (FixedClock not injected) |
| U-DATE-1 | U | Date resolution | "June 12th"@2026-08-04 → 2026-06-12; "December 3"@2026-08-04 → 2025-12-03; "8/4/2026" → 2026-08-04; "2026-06-12"; "Jun 12, 2025"; "April" → None; "last spring" → None; "" → None; "February 30" → None |
| U-POL-1 | U | Policy loader | non-simulated policy rejected; unknown evaluator rejected; unknown fact_type rejected |
| I-RUL-1 | I | Readiness live in responses | approve LVEF → response `prior_auth.requirements[R4].status == SATISFIED` |
| I-RUL-2 | I | `readiness_changed` audit only on change | approve a symptom → no readiness event; approve LVEF → event with `changes=[{R4, MISSING, SATISFIED}]` |

## 6. Note generation

| ID | Lvl | Case | Expected |
|---|---|---|---|
| U-NOTE-1 | U | Golden approve-all text | 4 sections match snapshot; every line has ≥1 fact_id; all fact_ids approved |
| U-NOTE-2 | U | Negation/uncertainty phrasing | "Denies orthopnea." · "Denies prior diagnosis of atrial fibrillation." · "Possible dizziness — …" |
| U-NOTE-3 | U | Rejected facts absent | reject dizziness → no dizziness line |
| U-NOTE-4 | U | Planned vs hypothetical | "Start ivabradine 5 mg twice daily." vs "Consider ivabradine in the future." |
| I-NOTE-1 | I | Override lifecycle | edit → `is_overridden`; change a fact → `override_stale`; revert → generated; accept → `accepted`; change fact → `acceptance_stale` |
| I-NOTE-2 | I | Revert when not overridden | 409 `invalid_transition` |

## 7. FHIR transformation

| ID | Lvl | Case | Expected |
|---|---|---|---|
| U-FHIR-1 | U | Golden bundle snapshot | after E2E-1 review decisions (dizziness rejected): matches snapshot (excluding `Bundle.id`, `timestamp`); counts Patient 1, Encounter 1, Condition 2, Observation 5, MedicationStatement 5, MedicationRequest 1 |
| U-FHIR-2 | U | Structural validity | every entry parses with `fhir.resources` R4B model of its type; Bundle parses |
| U-FHIR-3 | U | Determinism | map twice with different export ids/timestamps → entries identical |
| U-FHIR-4 | U | References resolve | every `reference` is the `fullUrl` of an entry in the bundle |
| U-FHIR-5 | U | Unverified codes → text only | with default terminology table: no `coding` for LOINC/SNOMED/ICD/RxNorm systems; `text` present. Flip one code to verified in test → coding emitted |
| U-FHIR-6 | U | Assertion mapping | AF negated → Condition `verificationStatus=refuted`, no clinicalStatus; uncertain LVEF → Observation `preliminary` |
| U-FHIR-7 | U | Exclusions | hypothetical med, symptoms, bb status appear in `excluded` with reasons, not in bundle |
| U-FHIR-8 | U | Ranges | LVEF 20–25 → `valueRange` low/high, no `valueQuantity` |
| U-FHIR-9 | U | Synthetic tagging | Patient has `meta.tag` synthetic; identifier system `urn:cardioflow:synthetic-mrn` |
| I-FHIR-1 | I | Export gate | pending facts → 409 `export_blocked` with fact ids; audit `export.blocked` |
| I-FHIR-2 | I | Export snapshot + staleness | generate → `is_stale=false`, stage `exported`; edit a fact → GET export `is_stale=true`, stage `review_complete` |
| I-FHIR-3 | I | Export immutable | after changes, old export bundle unchanged byte-for-byte |
| I-FHIR-4 | I | Readiness not a gate | ambiguous all reviewed, INCOMPLETE → export succeeds |

## 8. API behavior

| ID | Lvl | Case | Expected |
|---|---|---|---|
| I-API-1 | I | Create from fixture | 201; stage `transcript_ready`; audit `encounter.created` |
| I-API-2 | I | Unknown fixture | 404 `unknown_fixture` |
| I-API-3 | I | Paste transcript | valid lines → segments s1..sn with roles; bad line → 422 `transcript_parse_error` `details.line` |
| I-API-4 | I | Both fixture_id and transcript_text | 422 `validation_error` |
| I-API-5 | I | Extraction failure returns 200 | `CARDIOFLOW_MOCK_SCENARIO=invalid_json` → 200, stage `extraction_failed`, audit `extraction.failed` |
| I-API-6 | I | Error envelope | 404/409/422 all `{"error":{code,message,details}}`; no stack traces; FastAPI default 422 shape never leaks |
| I-API-7 | I | View shape | `EncounterView` validates against schema for every stage |
| I-API-8 | I | Stage derivation | walk golden: transcript_ready → in_review → review_complete → exported → (edit) review_complete |
| I-API-9 | I | Audit ordering | `seq` strictly increasing, no gaps, matches mutations 1:1 (+ readiness events) |
| I-API-10 | I | Persistence across app instances | create + approve with app A; new app B on same DB file → same view |
| I-API-11 | I | OpenAPI export | `/openapi.json` includes every route in ARCHITECTURE §10; `make gen-api` produces no diff in CI |
| I-API-12 | I | Anthropic config guard | provider=anthropic without model → app startup raises clear error |

## 9. Frontend components (Vitest + RTL)

| ID | Lvl | Case | Expected |
|---|---|---|---|
| C-SPAN-1 | C/U | `splitSegment` | no marks; one mark; adjacent marks; overlapping marks (runs carry both factIds); mark covering whole text |
| C-FIND-1 | C | FindingRow actions per status | pending: Approve/Edit/Reject; approved: Edit/Reject/Reopen; rejected: Reopen; clinician-origin approved: Edit/Reject |
| C-FIND-2 | C | Flag sentences | each ReviewFlag renders its sentence; hedged lists matched terms |
| C-FIND-3 | C | Null fields | render "not stated", never empty or "null" |
| C-FORM-1 | C | FactForm per type | renders typed controls for all 10 types; assertion options limited to allowed set; 422 errors mapped to fields |
| C-AUTH-1 | C | RequirementRow | chips for used ids; "Review candidate" for pending ids; "Add from chart" only for MISSING with fact_types; R2 shows context text |
| C-NOTE-1 | C | NoteSection states | generated / edited / edited+stale / accepted / accepted+stale tags and available actions |
| C-RAIL-1 | C | StageRail | each stage label for each WorkflowStage + readiness combination |
| C-KEY-1 | C | Keyboard | J/K move selection; A triggers approve mutation on selected pending; shortcuts ignored while typing in inputs |

## 10. End-to-end (Playwright, mock provider)

| ID | Case | Steps & assertions |
|---|---|---|
| E2E-1 | **Golden path** | PRODUCT_SPEC §2 steps 1–8 exactly: create → extract (18) → select LVEF, assert transcript `<mark>` contains "ejection fraction of 30 percent" and is in viewport → approve all except dizziness (reject w/ reason) → Authorization READY → edit HR 64 → R7 "Not met" and rail "Not met" → edit HR 78 → READY → note accept all + edit A&P → export → resource counts table → download JSON parses and has 15 entries → audit drawer shows `export.generated` |
| E2E-2 | **Adversarial path** | ambiguous: extract → 6 flagged in filter → LVEF detail shows "Spoken by the patient" → approve all → INCOMPLETE with R3/R5/R6 Missing → "Add from chart" on R6 → AF rhythm → overall "Not met" → export still allowed and bundle has no NYHA Observation |
| E2E-3 | Malformed output | backend with `CARDIOFLOW_MOCK_SCENARIO=invalid_json`: extract → failure panel text + raw output disclosure → "Add findings manually" → add LVEF from chart → Findings shows "Entered by clinician" |
| E2E-4 | Hallucinated output | `…=hallucinated`: notice "3 proposals were discarded" → details list shows the fake quote "an ejection fraction of 25 percent" → HR 72 shows value-not-in-evidence flag |
| E2E-5 | Staleness | golden: approve all → export → reject BP → rail "Out of date", Export banner visible, R9 Missing |
| E2E-6 | Evidence navigation | Authorization chip "NYHA class III" → Findings tab with fact selected (URL has `fact=`) → s19 highlighted |
| E2E-7 | Deep link | load `/encounters/{id}?tab=authorization` directly → Authorization visible |

E2E runs against a fresh DB per spec file (`CARDIOFLOW_DB_PATH` to a temp file, set in Playwright `webServer`).
Selectors: `data-testid` on rows (`finding-{fact_type}-{index}`), requirement rows (`requirement-R4`), stage items
(`stage-validate`), and text assertions for user-visible copy that the spec defines.

## 11. Verification commands

```
make test-backend     # pytest -q (unit + integration)
make lint             # ruff check backend && mypy backend/app && (cd frontend && npm run lint && npm run typecheck)
make test-frontend    # cd frontend && npm test -- --run
make e2e              # cd e2e && npx playwright test
make check            # all of the above
```
