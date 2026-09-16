# CardioFlow

CardioFlow is a local prototype that explores documentation and authorization workflow gaps in cardiology operations. It converts a synthetic encounter transcript into candidate clinical findings, links every finding to exact transcript evidence, and requires clinician review before a finding can affect a note, a documentation-readiness check, or a structured export.

Synthetic data only. Not for clinical use. The authorization workflow is a simulation and does not determine coverage.

## What works

1. Open a predefined synthetic encounter.
2. Run deterministic fixture-based extraction.
3. Inspect each candidate finding and its transcript span.
4. Approve, edit, reject, or reopen the finding.
5. Generate a note from approved findings.
6. For the HFrEF scenarios, evaluate approved findings against nine documented demo criteria.
7. Generate and download a FHIR R4 bundle from approved findings with explicit mapping exclusions.

The local application includes three fixtures:

- `hfref_golden`: complete HFrEF review, authorization-readiness, and export path.
- `hfref_ambiguous`: incomplete, conflicting, patient-recalled, and hypothetical evidence.
- `gerd_simulated`: general extraction, evidence review, note, and export without HFrEF authorization criteria.

Arbitrary transcript extraction is not implemented. The landing page includes a local speaker-format checker so this limitation is visible without sending or saving entered text. The configured mock provider only returns extraction results for the predefined fixtures.

## Evidence and review model

Transcript offsets and quoted text are stored with each candidate finding. The extraction pipeline rejects unknown segments, missing quotes, invalid values, and disallowed assertions. Extraction creates proposed state only.

A clinician action creates approved state, records the reviewer and time, and preserves the original evidence. Notes, authorization checks, and FHIR export read approved state. Proposed and rejected findings are excluded.

## Authorization criterion provenance

The HFrEF demonstration is a simulated documentation-readiness workflow. It is not an implementation of a named payer policy.

Each criterion stores its operator, threshold, unit, classification, verification date, source metadata, and a note explaining any demo-specific constraint. The interface keeps two evidence chains separate:

- Patient source: the approved finding and the supporting transcript turn.
- Criterion source: the document and section supporting the rule.

The current rule audit classifies:

- Authoritative-source support: chronic HFrEF, NYHA class II or III, resting heart rate at or above 70 bpm, and beta-blocker dose status.
- CardioFlow demo rules: requested medication documentation, cardiology encounter context, a 365-day LVEF documentation window, and encounter-specific rhythm documentation constraints.
- Unsupported or unclear: the exact 90/50 mmHg blood-pressure cutoff. The current FDA label refers to clinically significant hypotension without that numeric threshold.
- Payer-specific criteria: none. No real payer policy is represented.

Primary sources:

- [CORLANOR prescribing information on DailyMed](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=92018a65-38f6-45f7-91d4-a34921b81d0d), sections 1.1 and 4. Label revised August 2021; DailyMed record updated November 10, 2025.
- [2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure](https://professional.heart.org/-/media/832EA0F4E73948848612F228F7FA2D35.pdf), Management of Stage C HF: Ivabradine.

## FHIR export

The export is a FHIR R4 bundle generated from approved findings. Only mappings listed in the local terminology table create clinical resources. Approved findings without a verified mapping appear in the export exclusions list. The bundle does not imply that every finding has an external terminology code.

## Architecture

```text
Browser
  -> Next.js interface and same-origin /api proxy
  -> FastAPI application service
  -> typed encounter, finding, policy, note, and export models
  -> deterministic mock extraction provider
  -> SQLite persistence and append-only audit events
```

Key directories:

```text
backend/app/domain        Typed encounter, finding, and policy models
backend/app/extraction    Extraction contract, grounding, validation, and provider protocol
backend/app/policy        Deterministic engine and structured demonstration policy
backend/app/note          Approved-state note projection
backend/app/fhir          FHIR bundle generation and terminology table
backend/fixtures          Synthetic encounters and extraction outputs
frontend/src              Next.js interface and generated API types
```

## Local setup

Requirements: Python 3.11, Node.js, and npm.

```bash
make setup
make dev
```

Open [http://localhost:3000](http://localhost:3000). Browser API requests use the Next.js same-origin proxy, which targets `http://127.0.0.1:8010` by default. Startup checks report an API port conflict before launching the backend.

For a production-like local run:

```bash
make web-build
make start
```

## Verification

```bash
make check
make web-build
```

`make check` runs Ruff, mypy, TypeScript, backend tests, and frontend tests. Backend integration tests cover the golden HFrEF path, adversarial evidence, invalid extraction JSON, export exclusion behavior, heart-rate readiness transitions, GERD separation, FHIR structure, and criterion provenance.

## Limitations

- Extraction is fixture-based and deterministic. No external model is configured.
- Arbitrary transcript extraction is unavailable.
- Authorization results describe the configured demonstration rules only.
- The application has no authentication, multi-user permissions, production security controls, or deployment configuration.
- Synthetic encounter data is persisted in a local SQLite database during a run.
- This prototype has not been validated for clinical use.

The product and technical specifications remain available in [PRODUCT_SPEC.md](PRODUCT_SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and [TEST_PLAN.md](TEST_PLAN.md).
