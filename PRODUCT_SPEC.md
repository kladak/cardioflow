# CardioFlow — Product Spec

The clinician experience, screen by screen. Behavior rules live in [ARCHITECTURE.md](ARCHITECTURE.md); this doc
says what the person sees and does. All patients are synthetic.

## 1. Who and why

**User:** a cardiologist (or APP) finishing documentation for a heart-failure visit, with an MA/prior-auth
coordinator downstream. The observed problem: the facts a payer asks for (LVEF, NYHA class, rhythm, heart rate,
beta-blocker status) are *said* in the room, then re-hunted in the chart, re-typed into a note, and re-typed again
into an authorization form. Missing one means a denial and a callback days later.

**Promise:** in one screen, see what was said, what CardioFlow proposes, why, what you've approved, what is still
missing for the authorization, and exactly what structured data will leave.

**Not promised:** that the AI is right. The product is designed for the AI being wrong.

## 2. Golden path (the 3-minute demo)

Fixture `hfref_golden` (Ellis Varga, SYN-000142). Mock provider.

1. **Encounter.** Home → "New encounter" → choose *HFrEF follow-up — ivabradine start* → Create. Workspace opens,
   transcript on the left (26 turns), stage rail shows `Encounter ✓`, right side shows the Extract panel.
2. **Extract.** Click **Run extraction**. ≤1 s. Rail: `Extract ✓ 18 findings`. Right side switches to **Findings**.
   Transcript gains faint underlines wherever a finding cites it. Authorization readiness in the rail reads
   `Incomplete · 1/9` (only "Prescribed by cardiology", from encounter context).
3. **Review.** Findings are grouped (Diagnosis & function · Vitals & rhythm · Medications · History & symptoms).
   The one flagged item (*Dizziness — possible*, flags: hedged language, uncertain) sits at the top of its group
   with an amber marker.
   - Click **LVEF 30%**. Row expands; transcript scrolls to s16 and highlights "Your echo from June 12th showed an
     ejection fraction of 30 percent". Detail shows modality, date as spoken + resolved (`June 12th → 2026-06-12`),
     speaker Dr. Reyes. Press **A**. Row turns approved; rail readiness ticks to `2/9`; R4 flips to Satisfied.
   - `J` through the rest, approving. On *Furosemide 40*, the detail notes "unit not stated" — approve as is.
   - On *Dizziness*, the clinician judges it not clinically meaningful: press **R**, reason "Single orthostatic
     episode, not clinically relevant". Row greys out with strikethrough; its transcript mark disappears.
4. **Note.** Open **Note** tab. Four sections built only from approved findings. Hover "Resting HR 78 bpm." → the
   HR finding and s7 highlight. Edit *Assessment & Plan* to add "Recheck HR in 2 weeks." → section shows *Edited*.
   Accept all four sections. **Copy note**.
5. **Validate.** **Authorization** tab: `Ready — all 9 criteria documented` under the simulated-policy banner. Each row
   shows the evidence chips; clicking *NYHA class III* jumps to s19.
6. **Change something.** Back in Findings, edit **Resting HR** to 64 (e.g., re-measured). Rail immediately shows
   `Not met`; R7 row: "Resting heart rate 64 bpm is below 70 bpm." Note section *Objective* shows
   *Findings changed since accepted*. Edit HR back to 78 → Ready again. Audit drawer shows both edits and both readiness changes.
7. **Export.** **Export** tab: gate checklist all green → **Generate FHIR bundle**. Summary: 1 Patient, 1 Encounter,
   2 Conditions, 5 Observations, 5 MedicationStatements, 1 MedicationRequest; *Excluded: 4 findings (3 symptoms,
   1 beta-blocker status) — not mapped in v1*; *Text-only concepts* marker explains unverified codes. **Inspect bundle**
   opens the JSON inspector; selecting the LVEF Observation shows its `urn:cardioflow:fact` identifier with a
   "Show finding" link. **Download JSON**.
8. **Audit.** Header → **Audit** drawer: created → extraction completed (18 accepted) → 17 approvals, 1 rejection,
   2 edits, readiness changes, note edits/acceptances, export generated.

Resource counts above assume the rejection in step 3 and are asserted by E2E (TEST_PLAN E2E-1). (Conditions: HFrEF +
refuted AF history. Observations: LVEF, HR, BP, NYHA, rhythm. MedicationStatements: metoprolol, Entresto,
spironolactone, Farxiga, furosemide. MedicationRequest: ivabradine.)

## 3. Adversarial path

Fixture `hfref_ambiguous` (Nora Lindqvist, SYN-000287).

- Extraction proposes 9 findings; 6 are flagged. **No** NYHA class, rhythm, HF diagnosis, or beta-blocker status are proposed.
- *LVEF 20–25% · patient-reported · uncertain* shows flags: "Spoken by the patient, not a documented measurement",
  "Hedged language: 'like', 'maybe'", "Model marked low confidence".
- Approving everything as proposed yields `Incomplete`: R3/R5/R6 **Missing**, R1/R4/R8 **Needs review** with reasons
  ("Ivabradine mentioned as a possibility, not a decided plan"; "LVEF is patient-reported and uncertain";
  "On carvedilol; maximum-tolerated dose not documented").
- Missing rows offer **Add from chart**. Adding *Rhythm: atrial fibrillation (ECG)* with attestation "In-clinic ECG
  reviewed after visit" turns overall to `Not met`. The product never turns an absent NYHA class into a value.
- Malformed-output demos: start the backend with `CARDIOFLOW_MOCK_SCENARIO=invalid_json|item_errors|hallucinated`
  and run extraction on the golden fixture (§6.2).

## 4. Information architecture

### 4.1 Routes

| Route | Purpose |
|---|---|
| `/` | Encounter list + New encounter |
| `/encounters/[id]?tab=findings\|note\|authorization\|export&fact=<fact_id>` | Workspace. `tab` and `fact` live in the URL (deep-linkable, testable). |

Audit is a drawer inside the workspace, not a route.

### 4.2 Workspace layout (≥1280 px)

```
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ ← Encounters   Varga, Ellis · SYN-000142 · M · 65     HF follow-up · 4 Aug 2026 · Dr. A. Reyes  Audit │  header, 48px
├───────────────────────────────────────────────────────────────────────────────────────────────┤
│ ① Encounter ✓ ─ ② Extract ✓ 18 ─ ③ Review 12 of 18 · 1 flagged ─ ④ Validate Incomplete 5/9 ─ ⑤ Export Blocked │  stage rail, 44px
├───────────────────────────────────────┬───────────────────────────────────────────────────────┤
│ TRANSCRIPT                  26 turns  │ Findings   Note   Authorization   Export              │
│                                       │ ───────────────────────────────────────────────────── │
│ s16 Dr. Reyes                         │ All 18 · Pending 6 · Flagged 1 · Approved 11 · Rej. 1  │
│  Your echo from June 12th showed an   │                                                        │
│  ▓ejection fraction of 30 percent▓,   │ DIAGNOSIS & FUNCTION                                   │
│  about where it was in the hospital.  │ ✓ HF diagnosis   Chronic HFrEF        Dr. Reyes · s18  │
│  The ECG we did today shows normal    │ ▸ LVEF           30% · echo · 12 Jun   Dr. Reyes · s16 │
│  sinus rhythm.                        │   ┌ evidence, flags, rationale, actions ────────────┐ │
│                                       │   └──────────────────────────────────────────────────┘ │
│ s17 E. Varga                          │ ○ NYHA class     III                  Dr. Reyes · s19  │
│  So it hasn't gotten better.          │ VITALS & RHYTHM …                                      │
│              (scrolls independently)  │                  (scrolls independently)               │
└───────────────────────────────────────┴───────────────────────────────────────────────────────┘
          ~42%                                               ~58%
```

- Transcript is always visible: it is the ground truth the clinician checks against.
- The right surface's tabs map to stages: Findings + Note = Review, Authorization = Validate, Export = Export.
  Before a successful extraction the right surface shows the **Extract panel** instead of tabs.
- Stage rail items are buttons that open the corresponding tab. Each shows a real count/status, never decoration.
- 1024–1279 px: same two panes at 45/55. <1024 px: transcript collapses into a toggleable pane above tabs
  (not optimized; desktop is the target).

### 4.3 Stage rail states

| Stage | Shows |
|---|---|
| Encounter | ✓ always (encounter exists) |
| Extract | `Not run` · `Running…` · `Failed` (red text) · `✓ N findings` · `✓ N findings · M discarded` |
| Review | `—` before extraction · `K of N reviewed · F flagged` · `✓ All reviewed` |
| Validate | overall readiness word + `S/9` satisfied: `Ready` / `Needs review` / `Incomplete` / `Not met` |
| Export | `Blocked` (pending > 0) · `Ready to generate` · `✓ Generated 14:02` · `Out of date` |

## 5. Surfaces

### 5.1 Transcript pane

- Segment block: small caps speaker label + role (`Dr. Reyes · clinician`, `M. Ortiz, MA · staff`) and `s16`
  id in mono, then text. Patient turns have a slightly tinted left rule so speaker attribution scans quickly.
- **Evidence marks.** Every span of every non-rejected fact gets a mark: pending = dotted amber underline,
  approved = solid ink underline. Rejected facts' spans are unmarked. The **selected** fact's spans get a filled
  highlight and the pane scrolls the first span to ~30% from the top.
- Clicking a mark selects its fact. If multiple facts share overlapping text, a small popover lists them.
- Hovering a note line or a requirement chip applies a lighter "preview" highlight without scrolling.
- Header toggle "Evidence marks: on/off" (default on). Nothing else in the transcript is interactive; it is read-only.

### 5.2 Findings (review queue)

Groups (fixed order): **Diagnosis & function** (hf_diagnosis, lvef, nyha_class, beta_blocker_dose_status) ·
**Vitals & rhythm** (blood_pressure, resting_heart_rate, cardiac_rhythm) · **Medications** (active/held/discontinued,
then planned) · **History & symptoms** (condition_history, symptom). Within a group: flagged pending → pending →
approved → rejected, then transcript order.

**Row (collapsed, 40 px):** status glyph (○ pending, ◐ flagged pending, ✓ approved, ✎✓ approved-edited,
— rejected) · label · value summary in mono (`30% · echo · 12 Jun 2026`; `Metoprolol succinate 200 mg daily`;
`Atrial fibrillation — denied`) · assertion tag when not affirmed (`uncertain`, `denied`, `considering`) · source
(`Dr. Reyes · s16`, `Patient · s13`, or `Entered by clinician`).

**Row (expanded on select):**
1. *Evidence*: each quote as a block with `s16 · Dr. Reyes` — clicking scrolls transcript.
2. *Flags* (if any): plain-language sentences, e.g.
   `value_not_in_evidence` → "The value 72 does not appear in the quoted text."
   `patient_reported_measurement` → "Spoken by the patient, not a documented measurement."
   `hedged_language` → "Hedged language in the quote: 'maybe'." (list matched terms)
   `conflicting_candidates` → "Another proposed LVEF has a different value."
   `evidence_is_question` → "The only evidence is a question, not an answer."
   `model_low_confidence` → "The model marked this low confidence."
   `uncertain_or_hypothetical` → "Stated as uncertain." / "Mentioned as a possibility, not a decision."
3. *Model's note*: the rationale in muted text, labeled as the model's, collapsed to one line.
4. *Value detail*: all fields of the value, including nulls rendered as `not stated` (e.g. "Unit: not stated").
   LVEF shows `Date: "June 12th" → 2026-06-12` or `Date: not stated`.
5. *If edited*: "Edited — AI proposed: 25%".
6. *Actions*: **Approve** `A` · **Edit** `E` · **Reject** `R` (pending/approved) · **Reopen** `U` (approved/rejected).
   Exactly the transitions the API allows; unavailable actions are not rendered (not disabled-and-mysterious).

**Edit form** (inline, replaces value detail): typed controls generated per fact type — number inputs with
min/max from the schema, selects for enums (labels, not snake_case), text inputs for spoken-text fields, an
assertion select limited to allowed assertions. Shows "AI proposed" values beside each control. Save = approve with
edit. Esc cancels. Server 422 errors render under the offending control.

**Reject**: popover with optional reason textarea and Confirm (Enter). No modal.

**Single-value conflict (409)**: inline message under actions: "An approved LVEF (30%) already exists. Reject or
reopen it first." with a link that selects that fact.

**Add finding** (button at the top of Findings, and "Add from chart" from Authorization): inline form at the top of
the list — fact type select (preset when launched from a requirement), typed value controls, assertion, required
"Source / attestation" text ("Per echo report in EHR, 12 Jun 2026"). Saved facts show *Entered by clinician* and
no transcript marks.

**Filter bar**: `All · Pending · Flagged · Approved · Rejected` with counts. Default `All`.

**Keyboard** (when focus is in the workspace, not in an input): `J/K` next/previous finding · `A` approve · `E` edit ·
`R` reject · `U` reopen · `Esc` collapse · `1–4` switch tabs · `?` shortcut sheet.

### 5.3 Note

- Four sections: Subjective, Objective, Medications, Assessment & Plan. Each: title · state tag · lines · actions.
- State tags: `Generated` · `Edited` · `Edited · findings changed` (amber) · `Accepted` · `Accepted · findings changed` (amber).
- Generated lines render one per line; hovering highlights cited findings (outline in Findings if visible) and
  preview-highlights transcript spans. Clicking a line selects its first cited finding.
- Placeholder when empty: "No approved findings for this section yet" + "3 findings for this section await review →"
  if pending. Placeholders are visibly not note text (italic, muted, not copied).
- Actions: **Edit** (textarea prefilled with effective text; Save/Cancel) · **Revert to generated** (only when
  overridden; confirms inline) · **Accept** (only when not accepted or acceptance stale). In overridden+stale
  state, a "Show current generated text" disclosure shows the new generated lines for comparison.
- Header: **Copy note** (copies all effective texts with headings; toast "Note copied").
- Edited text has no line-level provenance; the UI says "Edited text is not linked to findings".

### 5.4 Authorization

Top, always: a quiet bordered banner — **Simulated policy.** "Demonstration criteria written for CardioFlow. Not a
real insurer's policy; not a coverage determination." Then policy name, payer display, version, and a "View
criteria source" disclosure showing the policy JSON.

**Readiness headline** — one sentence driven by `overall`:
- READY: "All 9 criteria are documented by approved findings."
- NEEDS_REVIEW: "No criteria are missing, but 2 need clinician review."
- INCOMPLETE: "3 criteria have no approved documentation. 2 need review."
- NOT_MET: "1 criterion is not met by the approved findings."

**Requirement table** (rows sorted by policy order, not by status — stable positions matter when statuses flip):

| Status | Criterion | Explanation | Evidence |
|---|---|---|---|
| ✓ Satisfied | LVEF ≤ 35% within 12 months | LVEF 30% (echocardiogram, 2026-06-12, 53 days before visit) is at or below 35%. | [LVEF 30%] |
| ○ Missing | NYHA class II–III | No approved NYHA class. | Add from chart · Review candidate → |
| ! Needs review | Beta-blocker optimized | On carvedilol; maximum-tolerated dose not documented. | [Carvedilol 12.5] |
| ✕ Not met | Resting heart rate ≥ 70 bpm | Resting heart rate 64 bpm is below 70 bpm. | [HR 64] |

- Status is glyph + word + color (never color alone).
- Evidence chips = `used_fact_ids` (approved). Clicking a chip switches to Findings with that fact selected (URL
  `?tab=findings&fact=…`) and highlights transcript evidence. The chip tooltip shows the primary quote.
- `pending_fact_ids` → "Review candidate →" link(s).
- R2 shows "From encounter context: specialty = cardiology".
- A row that just changed status briefly shows a subtle background pulse (≤600 ms, respects reduced-motion) and is
  announced via `aria-live="polite"`.

### 5.5 Export

**Before generating:** a checklist bound to `export.blocked_reasons`:
- "All findings reviewed" ✓ / "6 findings still pending → Review"
- "At least one approved finding" ✓
Note: "Authorization readiness is not required to export. The note is not included in the bundle."
**Generate FHIR bundle** (primary button; disabled only when `can_export=false`, with the checklist explaining why).

**After generating:** summary header "FHIR R4 bundle · generated 14:02 by Dr. A. Reyes · from review revision 23".
- Resource table: type · count · linked findings.
- **Excluded findings** list with reasons (from `excluded`).
- **Text-only concepts** note: "Codes are omitted until verified; concepts are sent as text."
- **Out of date** banner when `is_stale`: "Approved findings changed after this bundle was generated." + Generate again.
- Secondary: **Inspect bundle** → inspector (below) · **Download JSON** (real file) · **Copy JSON**.

**Bundle inspector** (secondary technical surface, visually plain): left list of entries (`Observation · LVEF`),
right pretty-printed JSON in mono with collapsible objects. Selecting an entry shows its manifest `fact_ids` as
"Show finding" links. No syntax-highlight theme beyond muted keys/values.

### 5.6 Extract panel (before a usable run)

- Idle: one-sentence explanation — "CardioFlow proposes findings from this transcript. Nothing is saved to the
  record until you approve it." Provider line: "Provider: Mock (deterministic fixture)" or "Provider: Anthropic ·
  {model}". **Run extraction**.
- Running: button shows progress text "Extracting…"; for Anthropic add "This can take up to a minute." Transcript
  remains usable. No fake progress bar.
- Failed: see §6.

### 5.7 Audit drawer

Right-side drawer, 420 px, over the work surface. Reverse-chronological list: time · actor · summary. Events with
`fact_id` link to the finding. `readiness_changed` expands to the per-requirement from→to list. Extraction events
expand to issue counts. Close with Esc.

### 5.8 Encounter list (`/`)

Table: patient (synthetic badge) · date · visit type · stage · readiness · updated. Row click opens workspace.
**New encounter** section (inline, above table): radio list of fixtures (title + one-line description + "golden" /
"adversarial" tag) → **Create**. Disclosure "Paste a transcript" → patient fields (given, family, birth date, gender,
MRN auto-suggested `SYN-` + 6 digits), visit type, date, textarea with the `ROLE: text` format hint → **Create**.
Footer on every page: "Synthetic data only. Not for clinical use."

## 6. Failure and edge behavior

### 6.1 Principles

- Say what happened, what it means for the record, and the next action. No "Something went wrong".
- Never show a partial result as if it were complete.
- Absence is shown as absence ("not stated", "Missing"), never filled.

### 6.2 Extraction outcomes

| Outcome | UI |
|---|---|
| `failed` — invalid_json / envelope_invalid | Extract panel, red rule: "The model's response couldn't be used — it was not valid JSON. No findings were created." Details disclosure: issues list + raw output (mono, scrollable). Actions: **Retry extraction** · **Add findings manually** (opens Findings tab with Add finding). |
| `failed` — provider_error | "Couldn't reach the extraction provider ({message}). No findings were created." Same actions. |
| `succeeded_with_issues` | Findings tab notice (amber rule, dismissible per session): "4 findings proposed. 3 proposals were discarded: 2 quoted text not found in the transcript, 1 cited a transcript line that doesn't exist." **Show details** lists each issue with fact_type and the model's quote. |
| `succeeded` with 0 findings | Findings empty state: "No findings were proposed for this transcript." + Add finding. |
| Low confidence / hedged / patient-reported | Flag marker on row; reasons in detail. Fact is otherwise normal. |

### 6.3 Review/API errors

| Error | UI |
|---|---|
| 409 revision_conflict | Refetch; toast "This encounter changed elsewhere — refreshed." Action not retried automatically. |
| 409 single_value_conflict | Inline under actions (§5.2). |
| 409 extraction_not_allowed | Not reachable via UI (button hidden when `can_run=false`); if hit, toast with message. |
| 409 export_blocked | Checklist refreshes; toast "Export blocked: 2 findings pending." |
| 422 on edit/add | Inline field errors. |
| Network / 5xx | Inline banner at top of the work surface with **Retry**; last good view stays visible. |

### 6.4 Staleness

| Situation | Where shown |
|---|---|
| Note section edited then findings changed | Section tag `Edited · findings changed` + comparison disclosure |
| Note section accepted then findings changed | Tag `Accepted · findings changed`; Accept button returns |
| Export generated then findings changed | Rail `Out of date`; Export tab banner; bundle still viewable, labeled out of date |

## 7. Visual direction

"Clinical paper": calm, dense, typographic. Tokens in `frontend/design-tokens.css`.

- Background warm off-white; work surfaces white with 1 px hairline borders; no drop shadows except popovers/drawer.
- Type: IBM Plex Sans (UI, 14 px base, 13 px dense rows) and IBM Plex Mono (values, ids, JSON).
- One accent (ink blue) for selection and primary actions. Status colors are muted inks, paired with glyphs and words.
- Radius 4 px. No gradients, glass, glows, orbs, sparkle icons, or "AI" badges. The AI is described in words where it
  matters ("Proposed by extraction", "Model's note").
- Cards are not the layout primitive. Use rows, rules, and whitespace. The only boxed elements: expanded finding
  detail, banners, inputs, drawer.
- Motion: ≤150 ms for expand/collapse; highlight scroll smooth; honor `prefers-reduced-motion`.
- Accessibility: WCAG AA contrast; visible focus rings (2 px accent); all actions keyboard-reachable; `aria-live`
  for readiness and toast; transcript marks are `<mark>` with `aria-describedby` to the finding label.

## 8. Component inventory

`frontend/src/`:

```
app/page.tsx                         EncounterListPage
app/encounters/[id]/page.tsx         Workspace (reads tab/fact from URL)
components/workspace/Header.tsx      patient + context + Audit button
components/workspace/StageRail.tsx
components/transcript/TranscriptPane.tsx  Segment.tsx  EvidenceMark.tsx   (span splitting util in lib/spans.ts)
components/extract/ExtractPanel.tsx  ExtractionIssues.tsx
components/findings/FindingsPane.tsx FindingRow.tsx FindingDetail.tsx FlagList.tsx
components/findings/FactValue.tsx    (per-type summary + detail formatter)
components/findings/FactForm.tsx     (per-type typed fields; used by Edit and Add)
components/note/NotePane.tsx         NoteSection.tsx
components/authorization/AuthorizationPane.tsx RequirementRow.tsx FactChip.tsx
components/export/ExportPane.tsx     BundleInspector.tsx
components/audit/AuditDrawer.tsx
components/ui/  Button.tsx StatusGlyph.tsx Toast.tsx Popover.tsx  (hand-rolled, minimal; no component library)
lib/api.ts (typed fetch client) · lib/api-types.ts (generated) · lib/queries.ts (TanStack hooks) · lib/labels.ts
lib/spans.ts (split segment text into marked/unmarked runs from EvidenceSpans; handles overlaps)
lib/keyboard.ts
```

State: server state only in TanStack Query (`['encounter', id]`, `['encounters']`, `['audit', id]`,
`['export', id, exportId]`); mutations `setQueryData(['encounter', id], response)` and invalidate `['audit', id]`.
UI state: `tab`, `fact` in URL; hover/preview and filter in component state. No global store.

`lib/spans.ts` contract: `splitSegment(text, marks: {start,end,factId,status}[]) -> Run[]` where each Run has
`text` and `factIds[]`; boundaries at every mark start/end; covered by unit tests (overlap, adjacency, full-segment).
