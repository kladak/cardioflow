# Implemented vertical slice

This file records the implemented scope rather than proposing future infrastructure.

1. **Typed foundation** — strict Pydantic encounter, transcript, finding, review, policy, note, audit, and export models.
2. **Fixture extraction** — deterministic provider, versioned contract, evidence grounding, validation, and review flags.
3. **Review workflow** — approve, typed edit, reject, and reopen actions with optimistic revisions and preserved provenance.
4. **Reviewed-state projections** — deterministic note, HFrEF-only documentation checks, and approved-state-only FHIR export.
5. **Persistence and audit** — SQLite aggregate persistence, transactional event writes, unique event sequence, and database triggers preventing audit update/delete.
6. **Operational interface** — Next.js landing page, guided/adversarial/GERD paths, evidence highlighting, current-action guidance, policy provenance, export inspection, retryable errors, and responsive layout.
7. **Verification** — backend invariant/integration tests, frontend behavior tests, strict type checks, linting, FHIR structural validation, production build, and CI.

## Release maintenance rule

Changes before the first portfolio release should correct behavior, claims, provenance, reproducibility, security hygiene, accessibility, or material UX comprehension. They should not add product breadth or speculative infrastructure.

## Explicitly not implemented

Live model extraction, arbitrary transcripts, authentication, multi-user behavior, payer connections, production deployment, FHIR server submission, externally verified terminology mapping, and clinical validation are out of scope.
