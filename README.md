# CardioFlow

AI-native cardiology encounter documentation workflow — a focused demo that sits beside an EHR.

```
Encounter → Extract → Review → Validate → Export
```

A synthetic heart-failure encounter enters as a transcript. CardioFlow proposes clinical findings with
transcript evidence, the clinician approves/edits/rejects them, deterministic rules check documentation readiness
against an explicitly **simulated** prior-authorization policy, and approved state is exported as FHIR R4.

> **AI proposes. Structured state validates. The clinician approves. Deterministic software acts.**

**Synthetic data only. Not a medical device. Not for clinical use. The authorization policy is fictional.**

## Status

Working local vertical slice. The deterministic mock workflow supports fixture creation, grounded extraction,
clinician review (approve/reject/edit/reopen), live simulated-policy readiness, deterministic note projection,
audit history, and approved-state-only FHIR R4 export.

| Doc | For |
|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Start here if you're building it |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System behavior, boundaries, contracts, decisions |
| [PRODUCT_SPEC.md](PRODUCT_SPEC.md) | Clinician experience, states, failure behavior |
| [TEST_PLAN.md](TEST_PLAN.md) | Test matrix and adversarial cases |

## Quick start

```bash
make setup
make dev
```

Open http://localhost:3000. Browser API requests remain same-origin and are
proxied to the CardioFlow service at http://127.0.0.1:8010. Use the
`HFrEF follow-up — ivabradine start` fixture for the golden path. Run `make test-backend` and
`cd frontend && npm run build` to verify the slice.

For a production-like local run, build first, then start both services:

```bash
make web-build
make start
```

## Layout

```
backend/app/domain        typed domain model (facts, encounter, policy)   ← authoritative
backend/app/extraction    LLM contract, prompt, provider protocol
backend/app/api           HTTP schemas
backend/app/policy        simulated policy JSON
backend/app/fhir          terminology table (codes unverified → text-only)
backend/fixtures          synthetic encounters, mock model outputs, expected outcomes
frontend                  design tokens (Next.js app created in Phase 0)
```
