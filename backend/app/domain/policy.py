"""Simulated prior-authorization policy + evaluation result types.

A policy is DATA (JSON under app/policy/policies/). Each requirement names one
registered, deterministic Python evaluator plus parameters. There is no rule DSL.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.facts import Drug, FactType, Strict


class RequirementStatus(StrEnum):
    SATISFIED = "SATISFIED"
    MISSING = "MISSING"  # no approved fact that could answer the requirement
    NOT_MET = "NOT_MET"  # approved facts affirmatively fail the criterion
    REQUIRES_REVIEW = "REQUIRES_REVIEW"  # approved facts exist but are uncertain / conflicting / out of scope


class OverallReadiness(StrEnum):
    READY = "READY"  # every requirement SATISFIED
    NEEDS_REVIEW = "NEEDS_REVIEW"  # ≥1 REQUIRES_REVIEW, no MISSING, no NOT_MET
    INCOMPLETE = "INCOMPLETE"  # ≥1 MISSING, no NOT_MET
    NOT_MET = "NOT_MET"  # ≥1 NOT_MET


class EvaluatorName(StrEnum):
    REQUESTED_MEDICATION = "requested_medication"
    CONTEXT_SPECIALTY = "context_specialty"
    HF_DIAGNOSIS = "hf_diagnosis"
    LVEF_AT_MOST = "lvef_at_most"
    NYHA_IN = "nyha_in"
    SINUS_RHYTHM = "sinus_rhythm"
    HEART_RATE_AT_LEAST = "heart_rate_at_least"
    BETA_BLOCKER_OPTIMIZED = "beta_blocker_optimized"
    BLOOD_PRESSURE_AT_LEAST = "blood_pressure_at_least"


class ProvenanceClassification(StrEnum):
    SUPPORTED = "supported_by_authoritative_source"
    PAYER_SPECIFIC = "payer_specific"
    DEMO_RULE = "application_specific_demo_rule"
    UNSUPPORTED = "unsupported_or_unclear"


class CriterionSourceType(StrEnum):
    FDA_LABEL = "fda_prescribing_information"
    PROFESSIONAL_GUIDELINE = "professional_guideline"
    PAYER_POLICY = "payer_policy"
    APPLICATION_SPECIFICATION = "application_specification"


class CriterionSource(Strict):
    title: str
    organization: str
    url: str
    section: str
    version_or_date: str
    source_type: CriterionSourceType


class PolicyRequirement(Strict):
    id: str = Field(pattern=r"^R\d+$")
    title: str
    policy_text: str  # human-readable criterion shown in the UI
    evaluator: EvaluatorName
    params: dict[str, Any] = Field(default_factory=dict)
    fact_types: list[FactType]  # which fact types can answer it (drives "Add from chart" + pending links)
    operator: str
    threshold: Any | None = None
    unit: str | None = None
    provenance_classification: ProvenanceClassification
    provenance_note: str
    criterion_sources: list[CriterionSource] = Field(default_factory=list)
    last_verified_at: date

    @model_validator(mode="after")
    def authoritative_classifications_require_matching_sources(self) -> PolicyRequirement:
        source_types = {source.source_type for source in self.criterion_sources}
        if self.provenance_classification is ProvenanceClassification.SUPPORTED and not source_types.intersection(
            {CriterionSourceType.FDA_LABEL, CriterionSourceType.PROFESSIONAL_GUIDELINE}
        ):
            raise ValueError("authoritatively supported criteria require an FDA label or professional guideline source")
        if (
            self.provenance_classification is ProvenanceClassification.PAYER_SPECIFIC
            and CriterionSourceType.PAYER_POLICY not in source_types
        ):
            raise ValueError("payer-specific criteria require a payer policy source")
        return self


class AuthorizationPolicy(Strict):
    id: str
    version: str
    simulated: Literal[True]  # a non-simulated policy cannot be loaded
    display_name: str
    payer_display: str
    disclaimer: str
    medication: Drug
    indication_text: str
    requirements: list[PolicyRequirement] = Field(min_length=1)


class RequirementEvaluation(Strict):
    requirement_id: str
    status: RequirementStatus
    explanation: str  # deterministic template output; never model-generated
    used_fact_ids: list[str] = Field(default_factory=list)  # approved facts that determined the status
    pending_fact_ids: list[str] = Field(default_factory=list)  # pending candidates of relevant types (links only)
    missing_fact_types: list[FactType] = Field(default_factory=list)
    context_fields_used: list[str] = Field(default_factory=list)  # e.g. ["context.specialty"]


class PriorAuthEvaluation(Strict):
    policy_id: str
    policy_version: str
    review_revision: int  # the fact state this evaluation reflects
    overall: OverallReadiness
    requirements: list[RequirementEvaluation]
