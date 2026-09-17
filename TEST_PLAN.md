# CardioFlow verification plan

This document describes current automated coverage and the manual release check. It does not claim tests that are absent from the repository.

## Automated commands

```bash
make check
make web-build
```

`make check` runs Ruff, mypy, TypeScript, pytest, and Vitest/React Testing Library. `make web-build` performs a Next.js production build using the same explicit backend origin as local startup.

## Backend invariants

The test suite covers:

- fixture and extraction-contract parsing, exact quote grounding, type/assertion validation, and adversarial omissions;
- safe invalid-JSON extraction with no proposed state;
- proposals and rejected/reopened findings excluded from policy evaluation;
- edited values, rather than original proposals, used by deterministic checks;
- the complete golden flow and heart-rate `64 -> NOT_MET`, `78 -> READY` transition;
- GERD note/export behavior with no HFrEF policy, evaluation, or readiness audit events;
- FHIR R4 structural parsing, internal reference integrity, approved-state manifest coverage, explicit exclusions, range representation, uncertainty status, and medication units;
- policy classifications and required authoritative metadata;
- SQLite revision conflicts and database-enforced append-only audit rows.

## Frontend behavior

Component tests cover initial API failure and retry, fixture loading, successful and failed encounter creation, loading-state termination, navigation, finding status/technical-detail presentation, evidence/provenance labels, policy-source links, and omission of HFrEF controls for GERD.

## Manual release check

Run a production-like local build, then verify:

1. Landing page explains the synthetic fixture workflow and contains no duplicated warning or horizontal overflow at desktop and narrow widths.
2. Golden HFrEF: extract; select a finding; confirm exact highlight; approve/edit/reject/reopen; finish review; verify criterion and patient provenance; verify 64/78 heart-rate transition; generate and inspect/download FHIR.
3. Adversarial HFrEF: confirm flags explain uncertainty/conflict/recalled/hypothetical language and no proposal affects downstream output before review.
4. GERD: confirm evidence review, note, and export are available but no HFrEF documentation stage or readiness events appear.
5. Browser console stays clear during normal paths; stopping the API yields a finite inline error and retry recovers after restart.

## Clean-clone gate

In an isolated checkout with no virtual environment, `node_modules`, SQLite database, or prior build output, run:

```bash
make setup
make check
make web-build
PORT=3123 API_PORT=8123 CARDIOFLOW_API_ORIGIN=http://127.0.0.1:8123 make start
```

Confirm `http://127.0.0.1:3123/api/health` returns the mock provider health response through the same-origin proxy.
