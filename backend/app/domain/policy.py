"""Simulated prior-authorization policy + evaluation result types.

A policy is DATA (JSON under app/policy/policies/). Each requirement names one
registered, deterministic Python evaluator plus parameters. There is no rule DSL.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

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


class PolicyRequirement(Strict):
    id: str = Field(pattern=r"^R\d+$")
    title: str
    policy_text: str  # human-readable criterion shown in the UI
    evaluator: EvaluatorName
    params: dict[str, Any] = Field(default_factory=dict)
    fact_types: list[FactType]  # which fact types can answer it (drives "Add from chart" + pending links)


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
