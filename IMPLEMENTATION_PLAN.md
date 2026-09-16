# CardioFlow — Implementation Plan

For the implementation agent. Read in this order: this file → [ARCHITECTURE.md](ARCHITECTURE.md) →
[PRODUCT_SPEC.md](PRODUCT_SPEC.md) → [TEST_PLAN.md](TEST_PLAN.md) → `backend/app/domain/*.py`.

## Ground rules

1. **Every phase ends demonstrable** in the browser and green on `make check`. No phase is "backend only".
2. **Types first.** The domain, contract and API schemas already exist. Use them; don't redefine shapes. If one is
   wrong, change it *and* the doc section that describes it in the same commit.
3. **Frontend types are generated** (`make gen-api`). Never hand-write a DTO type.
4. **Downstream reads approved state only** (`approved_facts()` gate, ARCHITECTURE §3.1).
5. **No new infrastructure** (queues, ORMs, state libraries, component libraries, auth) without a written reason in
   the ARCHITECTURE decision log.
6. Tests named with TEST_PLAN ids. Expected values come from `fixtures/extraction/expected_outcomes.json` and snapshots.
7. `backend/tests/unit/test_contracts.py` must stay green throughout.
8. Keep a short `CHANGELOG.md` entry per phase: what's demoable, deviations from docs.

## What already exists

| Path | Status |
|---|---|
| `backend/app/domain/facts.py`, `encounter.py`, `policy.py` | Authoritative domain types with invariants |
| `backend/app/extraction/contract.py`, `prompt.py`, `providers/base.py` | LLM contract, prompt v1, provider protocol |
| `backend/app/api/schemas.py` | Request/response/error contracts |
| `backend/app/policy/policies/sim_ivabradine_hfref_v1.json` | Simulated policy (9 requirements) |
| `backend/app/fhir/terminology.py` | Candidate codes, all unverified |
| `backend/fixtures/encounters/*.json` | Golden + adversarial synthetic encounters |
| `backend/fixtures/extraction/*` | Mock outputs (default + 4 malformed scenarios) and `expected_outcomes.json` |
| `backend/tests/unit/test_contracts.py` | 14 passing contract tests |
| `frontend/design-tokens.css`, `frontend/README.md` | Visual tokens + frontend setup notes |
| `Makefile`, `.env.example` | Targets referenced below (some become functional in Phase 0) |

---

## Phase 0 — Foundation (target ≤ ½ day)

**Backend**
- `app/core/settings.py` (pydantic-settings, ARCHITECTURE §13), `clock.py` (`Clock`, `SystemClock`, `FixedClock`),
  `ids.py` (`new_id(prefix)`, `SequentialIds`).
- `app/api/errors.py`: `ApiError(code, message, status, details)` exception + handlers that emit `ErrorResponse`;
  re-wrap `RequestValidationError` as 422 `validation_error`; catch-all 500 `internal_error`.
- `app/main.py`: `create_app(settings: Settings | None = None) -> FastAPI`; CORS; `GET /api/health`; dependency
  providers `get_settings`, `get_clock`, `get_ids`, `get_store`, `get_provider` (overridable in tests).
- `tests/conftest.py`: `settings` (tmp DB), `client` (TestClient with FixedClock `2026-08-04T15:00:00Z` + SequentialIds).

**Frontend**
- Create Next.js app per `frontend/README.md` (TypeScript, App Router, Tailwind, ESLint, `src/`), keep existing files.
- Add `@tanstack/react-query`, `openapi-typescript` (dev), Vitest + RTL + jsdom (dev), IBM Plex via `next/font/google`.
- Wire `design-tokens.css` into Tailwind (theme variables) and `globals.css`.
- `lib/api.ts` (fetch wrapper: base URL, JSON, throws `ApiError` with parsed envelope), `lib/queries.ts` (QueryClient provider).
- `/` renders "CardioFlow" + API health line (`API ok · provider mock`) + synthetic-data footer.
- `scripts/gen-api` via `make gen-api`: start-less export — `python -c "from app.main import create_app; import json; print(json.dumps(create_app().openapi()))" > frontend/openapi.json && npx openapi-typescript frontend/openapi.json -o frontend/src/lib/api-types.ts`.

**E2E**
- `e2e/` Playwright project (Chromium; in this environment use `executablePath` from `/opt/pw-browsers` if needed),
  `webServer` starts uvicorn (temp DB) and `next dev`. Spec `E2E-0`: home shows "API ok".

**Done when**
- `make dev` starts API on :8000 and web on :3000; home page shows health.
- `make check` passes: contract tests, health test, ruff, mypy (app/), eslint, tsc, vitest (1 trivial test), E2E-0.
- `make gen-api` produces `api-types.ts` with `EncounterView`.

---

## Phase 1 — Smallest encounter path

Goal: pick a synthetic fixture, land in a workspace that shows the transcript.

**Backend**
- `store/sqlite.py`: schema (ARCHITECTURE §11), `create`, `load`, `list`, `save(encounter, events, expected_revision)`,
  `list_audit`. `RevisionConflict`, `NotFound`.
- `services/fixtures.py`: load `fixtures/encounters/*.json` at startup → `FixtureListItem` + builder.
- `services/transcript_parser.py`: `ROLE: text` parser (ARCHITECTURE §10 notes).
- `services/encounter_service.py`: `create_encounter(req)` (fixture xor paste) → `Encounter` (revision 0,
  review_revision 0, empty lists) + `encounter.created` audit.
- `services/view_builder.py`: `build_view(encounter, settings)` → `EncounterView` with stage derivation (full rules
  in `WorkflowStage` docstring), `extraction.can_run` (§5.6), `fact_counts`, `note_sections=[]`,
  `prior_auth=None`, `export=None`.
- Routes: `GET /api/fixtures`, `POST /api/encounters`, `GET /api/encounters`, `GET /api/encounters/{id}`,
  `GET /api/encounters/{id}/audit`.

**Frontend**
- `/`: fixture radio list + Create; paste-transcript disclosure; encounters table.
- `/encounters/[id]`: Header, StageRail (Encounter ✓, Extract "Not run", others "—"), TranscriptPane (no marks yet),
  right side ExtractPanel idle with **Run extraction** button *not rendered yet* (no fake controls) — show provider line only.

**Tests:** I-API-1..4, I-API-6 (404/422 cases), I-API-10, C-RAIL-1 (partial), E2E-0b: create golden → 26 segments visible.

**Done when:** creating either fixture opens a workspace showing the full transcript with speaker labels; reload
persists; list shows the encounter with stage `transcript_ready`.

---

## Phase 2 — Extraction & provenance (read-only findings)

Goal: run extraction and inspect every proposal against the transcript.

**Backend**
- `extraction/numbers.py` (digits, decimals, slashes, number words 0–199), `grounding.py` (§5.3), `flags.py` (§5.4),
  `pipeline.py` (§5.2), `providers/mock.py` (§5.1).
- `encounter_service.run_extraction(id, expected_revision)`: check `can_run` (else 409), run pipeline, replace pending
  extraction facts, append run, audit `extraction.completed|failed`, save.
- Route `POST /api/encounters/{id}/extraction-runs`.
- Facts ordering in view: catalog order, then first evidence segment seq.

**Frontend**
- ExtractPanel: idle / running / failed (issues + raw output disclosure, **Retry** only — "Add findings manually"
  arrives in Phase 3) per PRODUCT_SPEC §5.6, §6.2.
- Tabs appear after a usable run; only **Findings** enabled (other tabs are not rendered until their phase).
- FindingsPane with groups, filter bar (All/Pending/Flagged), FindingRow, FindingDetail (evidence, flags sentences,
  model's note, value detail with "not stated").
- `lib/spans.ts` + EvidenceMark: pending marks, selection highlight, scroll-to-span, click mark → select.
- URL `?tab=findings&fact=`.
- Succeeded-with-issues notice + details.

**Tests:** U-EXT-1..13, U-GRD-1..9, U-PROV-1..2, U-FLG-1..7, U-HAL-1..2, I-API-5, I-REV-12, C-SPAN-1, C-FIND-2, C-FIND-3,
E2E-4 (hallucinated notice + flag), E2E-3 partial (failure panel only).

**Done when:** golden shows 18 findings with correct highlights; selecting LVEF scrolls to and highlights s16; the three
malformed scenarios show the specified failure/notice states; ambiguous shows 6 flagged findings and none of the
forbidden types.

---

## Phase 3 — Review workflow

Goal: the clinician can approve, edit, reject, reopen, and add from chart.

**Backend**
- `review/transitions.py`: pure `apply(fact, action, request, actor, now, candidate_types) -> (Fact, review_revision_delta, AuditEvent draft)`; raises `InvalidTransition`, value `ValidationError`.
- `encounter_service.review_fact`, `add_fact`: expected_revision check, single-value check (409), apply, bump
  `revision`/`review_revision`, audit, save. Implement `approved_facts(encounter)` gate here.
- Routes: `POST …/facts/{fact_id}/review`, `POST …/facts`.
- View: `export` still None; `fact_counts` complete.

**Frontend**
- Actions per status (C-FIND-1), reject popover with reason, FactForm per type (edit + add), inline 409/422 handling,
  "Edited — AI proposed" line, approved marks styling, rejected marks removed.
- Add finding (top of Findings) + "Add findings manually" from failed extraction.
- Keyboard shortcuts (PRODUCT_SPEC §5.2), filters incl. Approved/Rejected.
- Revision-conflict toast + refetch.
- StageRail Review counts.

**Tests:** U-REV-1..4, I-REV-1..11, I-PROV-1..2, C-FIND-1, C-FORM-1, C-KEY-1, E2E-3 complete.

**Done when:** a full golden review (17 approve, 1 reject) is possible by keyboard alone; edits show AI-proposed values;
invalid edits show field errors; audit endpoint lists every action.

---

## Phase 4 — Deterministic prior-authorization readiness

Goal: readiness reacts live to review decisions, with evidence links.

**Backend**
- `policy/dates.py` (§7.4), `loader.py` (validate evaluator names exist in registry at startup), `evaluators.py` (§7.3),
  `engine.py` (`evaluate`, overall precedence).
- `view_builder`: `prior_auth` always computed → **tighten schema to non-optional** and regenerate TS types.
- `encounter_service`: after any mutation that changes `review_revision`, diff statuses vs `last_requirement_statuses`;
  write `prior_auth.readiness_changed` when different. Extraction creates only pending facts, so it never emits this event.
- Route `GET /api/policies/{policy_id}`.

**Frontend**
- AuthorizationPane: simulated-policy banner, readiness headline, requirement rows (policy order), explanations,
  FactChip → Findings selection, "Review candidate →", "Add from chart" (opens Add finding preset), R2 context text,
  status-change pulse + aria-live, policy JSON disclosure.
- StageRail Validate status.

**Tests:** U-RUL-1..16, U-DATE-1, U-POL-1, U-GATE-1 (policy/), U-GATE-2 (rules), U-HAL-3, I-RUL-1..2, I-PROV-4, C-AUTH-1,
E2E-6, E2E-2 (through INCOMPLETE → Add from chart → NOT_MET).

**Done when:** golden approve-all shows READY; editing HR to 64 flips R7 and overall to NOT_MET immediately; ambiguous
matches expected statuses with the specified explanations; every satisfied row links to transcript evidence.

---

## Phase 5 — Note review

**Backend**
- `note/labels.py` (display labels for enums, shared by note + FHIR text), `note/generator.py` (§8).
- `encounter_service.note_section_action` (edit / revert_to_generated / accept) + audit.
- View `note_sections` with override/acceptance staleness.
- Route `POST …/note-sections/{key}`.

**Frontend**
- NotePane + NoteSection (states, edit textarea, revert, accept, comparison disclosure), line hover → finding +
  transcript preview highlight, click → select, pending hint, Copy note.

**Tests:** U-NOTE-1..4, U-HAL-4, U-GATE-1 (note/), I-NOTE-1..2, C-NOTE-1.

**Done when:** golden note text matches snapshot after approvals; editing then changing a finding shows
"Edited · findings changed" without losing the edit; Copy note puts exactly the effective texts on the clipboard.

---

## Phase 6 — FHIR export

**Backend**
- **Terminology verification task:** look up each code in `fhir/terminology.py` at the listed source; set
  `status="verified"` and `verified_on` only for confirmed code+display pairs. Look up RxNorm ingredient CUIs for the
  catalog drugs in RxNav and add them only if confirmed. Record anything you could not verify in ARCHITECTURE §9.4.
  If no network access, leave all unverified — the product works text-only by design.
- `fhir/mapper.py` (§9.1–9.2), export gate, `encounter_service.create_export` + audit `export.generated|blocked`.
- View `export` → **tighten schema to non-optional**; stage `exported` derivation.
- Routes `POST …/exports`, `GET …/exports/{export_id}`.

**Frontend**
- ExportPane: gate checklist, Generate, summary table with finding links, exclusions, text-only concepts note,
  Out-of-date banner, BundleInspector (entry list + JSON + "Show finding"), Download JSON, Copy JSON.
- StageRail Export status.

**Tests:** U-FHIR-1..9, U-HAL-5, U-GATE-1 (fhir/), I-FHIR-1..4, I-PROV-3, E2E-5.

**Done when:** golden export has the 15 entries listed in PRODUCT_SPEC §2; every entry parses with `fhir.resources`;
editing any approved finding marks the export out of date; downloaded file equals `ExportDetail.bundle`.

---

## Phase 7 — Auditability & edge-case hardening

- AuditDrawer (PRODUCT_SPEC §5.7) with fact links and expandable payloads.
- Walk every row of PRODUCT_SPEC §6 tables in the browser against each mock scenario; fix copy/behavior gaps.
- I-API-6..9, I-API-11, I-REV-13; network-error banner with retry (simulate by stopping API).
- Verify no stack traces or raw Pydantic error shapes reach the UI.

**Done when:** every PRODUCT_SPEC §6 row is reproducible and matches; audit drawer tells the full golden story.

---

## Phase 8 — Optional model-backed extraction

- `providers/anthropic.py` (§5.1), add `anthropic` optional dependency, startup guard (I-API-12).
- `backend/scripts/smoke_extraction.py --fixture hfref_ambiguous`: runs real provider, prints run status, issues,
  flags, and asserts `must_not_extract` types are absent. Manual only; never in CI; requires `ANTHROPIC_API_KEY` and
  `CARDIOFLOW_ANTHROPIC_MODEL`.
- U-EXT-7 covers retry logic with a fake provider (no network).

**Done when:** with credentials, both fixtures extract through the same pipeline and UI; without credentials, nothing changes.

---

## Phase 9 — Visual polish & full E2E

- Apply PRODUCT_SPEC §7 consistently (spacing, type scale, status inks, focus rings, reduced motion).
- Accessibility pass: keyboard-only golden path; axe check via `@axe-core/playwright` on workspace tabs (no serious violations).
- E2E-1 (full golden), E2E-2 (full adversarial), E2E-7; all E2E green from a clean checkout.
- README: 3-minute demo script (PRODUCT_SPEC §2), screenshots optional.

**Done when:** `make check` is green from a clean clone; the golden demo runs end-to-end without explanation.

---

## Dependency graph

```
P0 ─► P1 ─► P2 ─► P3 ─┬─► P4 ─┐
                      ├─► P5 ─┼─► P7 ─► P9
                      └─► P6 ─┘
                 P8 (any time after P2; optional)
```
P4, P5, P6 are independent after P3 and can be done in any order; the recommended order (4 → 5 → 6) front-loads the
most distinctive behavior.

## Deliberately deferred (do not build)

Auth/users/roles · multiple policies or policy editor · payer submission · LLM note narrative · audio/ASR · transcript
editing · FHIR server/`$validate` integration · Composition/DocumentReference/Provenance resources · bulk approve ·
background jobs · dark mode · mobile layout optimization · i18n.
