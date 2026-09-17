# CardioFlow

[![CI](https://github.com/kladak/cardioflow/actions/workflows/ci.yml/badge.svg)](https://github.com/kladak/cardioflow/actions/workflows/ci.yml)

CardioFlow is a local software-engineering prototype for reviewing structured facts derived from synthetic clinical conversations. It converts fixture-based encounter evidence into proposed findings, keeps those proposals separate from clinician-reviewed state, and uses only approved findings for note projection, configured documentation-readiness checks, and FHIR R4 export.

All people and encounters are fictional. Not for clinical use. The HFrEF rules are a documentation-readiness demonstration, not a payer policy, coverage determination, clinical recommendation, or validated clinical system.

## Workflow and trust boundary

```text
Synthetic encounter
       |
Deterministic extraction
       |
Proposed findings + exact transcript spans
       |
Clinician approve / edit / reject
       |
Approved state
   /       |        \
Note   Demo rules   FHIR R4
```

The important architectural boundary is between **proposed** and **approved** state. Extraction never writes authoritative clinical state. Proposed and rejected findings cannot affect downstream outputs; edits replace the proposed value only in reviewed state, while preserving the original proposal and transcript provenance.

CardioFlow does not retrieve live evidence or search external sources during an encounter. Criterion citations are versioned metadata stored with the demonstration policy.

## What to try

The landing page exposes three packaged synthetic scenarios:

- **Guided HFrEF demo (`hfref_golden`)** — run extraction, select a finding to highlight its exact transcript span, review all findings, inspect the nine configured documentation checks, edit heart rate from 64 bpm (`NOT_MET`) to 78 bpm (`READY` when the other checks are met), then inspect or download the FHIR bundle.
- **Adversarial HFrEF demo (`hfref_ambiguous`)** — inspect conflicting, uncertain, recalled, and hypothetical statements. The fixture deliberately omits facts that are not grounded in the transcript and flags ambiguous proposals for review.
- **Simulated GERD encounter (`gerd_simulated`)** — review a predefined gastroenterology conversation, note projection, and supported FHIR output. HFrEF-specific checks are not computed.

Arbitrary-transcript extraction is not implemented. The landing-page text box only checks speaker-line formatting locally; it does not send, save, or extract the entered text.

## Run locally

Requirements: Python 3.11, Node.js 22, npm, and `make`.

```bash
git clone https://github.com/kladak/cardioflow.git
cd cardioflow
make setup
make check
make web-build
make start
```

Open [http://localhost:3000](http://localhost:3000). The browser calls the Next.js same-origin `/api` proxy, which targets `http://127.0.0.1:8010` by default. The startup command checks for an API port conflict before launching.

For development with reload:

```bash
make dev
```

To use different local ports:

```bash
API_PORT=8123 CARDIOFLOW_API_ORIGIN=http://127.0.0.1:8123 PORT=3123 make start
```

## Technology

- Next.js 16, React 19, TypeScript, generated OpenAPI client types
- FastAPI, Pydantic v2, typed domain models
- deterministic fixture provider with strict parsing, grounding, and review flags
- SQLite encounter persistence with revision checks and database-enforced append-only audit rows
- deterministic note and policy projections from reviewed state
- FHIR R4 bundle generation, with structural validation in tests using `fhir.resources`
- pytest, Vitest, React Testing Library, Ruff, mypy, and GitHub Actions

See [ARCHITECTURE.md](ARCHITECTURE.md) for the implemented boundaries and data flow.

## Policy provenance

The bundled `sim-ivabradine-hfref` policy is an application demonstration. Each check records its operator, threshold, classification, verification date, source metadata, and an explanatory provenance note. The UI keeps two evidence chains separate:

- **Patient evidence** — the approved value and its source transcript turn.
- **Criterion provenance** — the document context associated with a configured check.

The nine checks are classified as follows:

- **Authoritatively supported concepts/thresholds:** chronic HFrEF, NYHA class II or III, resting heart rate at least 70 bpm, and beta-blocker status.
- **Application-specific demonstration rules:** requested medication documentation, cardiology encounter context, the 365-day LVEF documentation window, detailed rhythm-documentation handling, and the 90/50 mmHg blood-pressure threshold.
- **Payer-specific rules:** none.

The BP distinction is deliberate. The [initial 2015 FDA label](https://www.accessdata.fda.gov/drugsatfda_docs/label/2015/206143orig1s000lbl.pdf) used a blood-pressure-below-90/50-mmHg contraindication. The [current DailyMed label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=92018a65-38f6-45f7-91d4-a34921b81d0d) instead says clinically significant hypotension without that number. CardioFlow retains 90/50 only as a deterministic demo threshold; it is not represented as current guidance or a coverage rule.

Other primary context includes the [2022 AHA/ACC/HFSA Heart Failure Guideline](https://professional.heart.org/-/media/832EA0F4E73948848612F228F7FA2D35.pdf). Source metadata was last reviewed on 2026-09-16.

## FHIR behavior

Export creates a FHIR R4 collection bundle from reviewed state. It uses synthetic identifiers, resolves internal Patient and Encounter references, represents supported clinical values with appropriate resource shapes, and lists approved facts without a supported mapping in an explicit exclusions array. It deliberately uses text-only clinical concepts where no verified terminology mapping is maintained.

Structural validation is not interoperability certification. The project does not claim conformance to an implementation guide, terminology validation, server acceptance, or production exchange readiness.

## Verification

```bash
make check       # Ruff, mypy, TypeScript, backend tests, frontend tests
make web-build   # Next.js production build
```

The backend suite proves the review boundary, edited-value use, reopen behavior, scenario separation, invalid extraction handling, rule transitions, FHIR mapping/exclusions/reference integrity, and database append-only audit enforcement. Frontend tests cover error recovery, encounter creation, evidence/provenance presentation, and HFrEF-versus-GERD workflow visibility. CI runs the same checks on pushes and pull requests.

The exact current coverage and manual verification paths are in [TEST_PLAN.md](TEST_PLAN.md).

## Limitations

- Every encounter and patient is synthetic.
- Extraction is deterministic and fixture-based; no external model or live retrieval service is configured.
- The policy is a demonstration configuration, not a payer policy or medical guidance.
- The app has no authentication, authorization, multi-user isolation, encryption configuration, production observability, or deployment setup.
- SQLite is appropriate for this local prototype, not a multi-user deployment.
- FHIR mappings are intentionally narrow and are not interoperability-certified.
- The software has not been clinically validated and must not be used for patient care.

The implemented design is documented in [ARCHITECTURE.md](ARCHITECTURE.md). [PRODUCT_SPEC.md](PRODUCT_SPEC.md) describes the shipped prototype’s scope; [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) records what was deliberately implemented or excluded.
