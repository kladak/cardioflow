# CardioFlow product scope

CardioFlow is an engineering prototype that demonstrates a bounded evidence-review workflow using only synthetic encounters.

## User outcome

A reviewer can open a fixture, run deterministic extraction, compare every proposed fact with exact transcript evidence, approve/edit/reject/reopen findings, and inspect downstream outputs derived only from approved state.

The shipped workflow is:

`Encounter -> Extract -> Review -> Validate documentation -> Export`

## Included scenarios

- `hfref_golden`: complete HFrEF demonstration, including configured ivabradine documentation checks and FHIR export.
- `hfref_ambiguous`: incomplete/conflicting/uncertain/recalled/hypothetical evidence to demonstrate safe failure and review behavior.
- `gerd_simulated`: gastroenterology evidence review, note projection, and supported export without HFrEF checks.

All patient identities and content are fictional. Arbitrary transcript extraction, live transcript generation, and live evidence retrieval are not included.

## Safety and comprehension requirements

- Proposed findings are visibly distinct from approved, edited, rejected, and flagged findings.
- Selecting a finding highlights its exact transcript evidence and exposes technical offsets only on demand.
- A proposed, rejected, or reopened fact cannot affect notes, configured checks, or FHIR resources.
- Patient evidence and criterion provenance are separate concepts in the interface.
- HFrEF output is labelled as simulated documentation readiness, never coverage or medical advice.
- FHIR exclusions are explicit and the interface does not imply every concept has terminology mapping.
- GERD cannot enter the HFrEF-specific policy workflow.
- Invalid extraction JSON produces an understandable failed run with no proposed facts.

## Deliberately excluded

Authentication, real patient data, clinical deployment, payer submission, general-purpose extraction, external model calls, extra conditions, cloud infrastructure, analytics, billing, and production claims are outside this repository’s scope.
