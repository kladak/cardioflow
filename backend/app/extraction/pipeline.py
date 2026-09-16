from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError

from app.domain.encounter import Encounter, ExtractionIssue, ExtractionIssueKind, ExtractionRun, ExtractionRunStatus
from app.domain.facts import CandidateFact, Fact, FactOrigin, FactType, ReviewState, ReviewStatus, assertion_allowed
from app.extraction.contract import ITEM_ADAPTER, ExtractionEnvelope
from app.extraction.flags import compute_flags
from app.extraction.grounding import ground
from app.extraction.prompt import PROMPT_VERSION
from app.extraction.providers.base import ExtractionProvider, ProviderError, ProviderRequest


def run_extraction(
    encounter: Encounter,
    provider: ExtractionProvider,
    now: datetime,
    id_fn: Callable[[str], str],
) -> tuple[ExtractionRun, list[Fact]]:
    issues: list[ExtractionIssue] = []
    raw_text = None
    model = None
    try:
        response = provider.extract(ProviderRequest(context=encounter.context, transcript=encounter.transcript))
        raw_text, model = response.raw_text, response.model
        try:
            obj = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            issues.append(ExtractionIssue(kind=ExtractionIssueKind.INVALID_JSON, message=f"Invalid JSON: {exc.msg}"))
            obj = None
        if obj is not None:
            try:
                envelope = ExtractionEnvelope.model_validate(obj)
            except ValidationError as exc:
                issues.append(
                    ExtractionIssue(
                        kind=ExtractionIssueKind.ENVELOPE_INVALID,
                        message="Extraction envelope did not match the contract",
                        detail={"errors": exc.errors(include_url=False)[:5]},
                    )
                )
                envelope = None
        else:
            envelope = None
    except ProviderError as exc:
        issues.append(ExtractionIssue(kind=ExtractionIssueKind.PROVIDER_ERROR, message=str(exc)))
        envelope = None
    candidates: list[tuple[FactType, CandidateFact]] = []
    if envelope:
        for index, raw in enumerate(envelope.facts):
            try:
                item = ITEM_ADAPTER.validate_python(raw)
            except ValidationError as exc:
                issues.append(
                    ExtractionIssue(
                        kind=ExtractionIssueKind.ITEM_INVALID,
                        item_index=index,
                        fact_type=str(raw.get("fact_type", "unknown")),
                        message="Proposal did not match the fact schema",
                        detail={"errors": exc.errors(include_url=False)[:5]},
                    )
                )
                continue
            fact_type = FactType(item.fact_type)
            if not assertion_allowed(fact_type, item.value, item.assertion):
                issues.append(
                    ExtractionIssue(
                        kind=ExtractionIssueKind.DISALLOWED_ASSERTION,
                        item_index=index,
                        fact_type=fact_type,
                        message="Assertion is not allowed for this fact type",
                    )
                )
                continue
            spans = []
            for ref in item.evidence:
                span, issue = ground(ref, encounter.transcript, index, fact_type)
                if issue:
                    issues.append(issue)
                elif span and span not in spans:
                    spans.append(span)
            if not spans:
                issues.append(
                    ExtractionIssue(
                        kind=ExtractionIssueKind.UNGROUNDED_FACT,
                        item_index=index,
                        fact_type=fact_type,
                        message="No evidence quote could be verified",
                    )
                )
                continue
            candidates.append(
                (
                    fact_type,
                    CandidateFact(
                        value=item.value,
                        assertion=item.assertion,
                        evidence=spans,
                        model_confidence=item.model_confidence,
                        rationale=item.rationale,
                    ),
                )
            )
    run_id = id_fn("run")
    facts: list[Fact] = []
    for fact_type, candidate in candidates:
        candidate.flags = compute_flags(fact_type, candidate, candidates)
        facts.append(
            Fact(
                id=id_fn("fct"),
                fact_type=fact_type,
                origin=FactOrigin.EXTRACTION,
                extraction_run_id=run_id,
                candidate=candidate,
                review=ReviewState(status=ReviewStatus.PENDING),
            )
        )
    if envelope is None or (issues and not facts):
        status = ExtractionRunStatus.FAILED
    elif issues:
        status = ExtractionRunStatus.SUCCEEDED_WITH_ISSUES
    else:
        status = ExtractionRunStatus.SUCCEEDED
    run = ExtractionRun(
        id=run_id,
        provider=provider.name,
        model=model,
        prompt_version=PROMPT_VERSION,
        started_at=now,
        completed_at=now,
        attempts=1,
        status=status,
        accepted_fact_ids=[f.id for f in facts],
        issues=issues,
        raw_output=raw_text,
    )
    return run, facts
