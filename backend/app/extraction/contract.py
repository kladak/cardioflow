"""The LLM extraction contract (schema_version cardioflow.extraction.v1).

The model returns ONLY: fact_type, value, assertion, evidence[{segment_id, quote}],
model_confidence, rationale. It never returns ids, offsets, statuses, flags,
codes, dates-as-dates, or anything downstream systems act on.

Validation is two-level (see ARCHITECTURE.md §5.2):
  1. ExtractionEnvelope  — strict; failure ⇒ run FAILED.
  2. ExtractedFactItem   — validated per item; failure ⇒ that item dropped + issue.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter

from app.domain.facts import (
    Assertion,
    BetaBlockerDoseStatusValue,
    BloodPressureValue,
    CardiacRhythmValue,
    ConditionHistoryValue,
    HfDiagnosisValue,
    LvefValue,
    MedicationValue,
    ModelConfidence,
    NyhaClassValue,
    RestingHeartRateValue,
    Strict,
    SymptomValue,
)

SCHEMA_VERSION = "cardioflow.extraction.v1"
MAX_FACTS = 60


class EvidenceRef(Strict):
    segment_id: str = Field(pattern=r"^s\d+$")
    quote: str = Field(min_length=3, max_length=300, description="Verbatim substring of that segment's text")


class _ItemBase(Strict):
    assertion: Assertion
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=3)
    model_confidence: ModelConfidence
    rationale: str | None = Field(default=None, max_length=280)


class HfDiagnosisItem(_ItemBase):
    fact_type: Literal["hf_diagnosis"]
    value: HfDiagnosisValue


class LvefItem(_ItemBase):
    fact_type: Literal["lvef"]
    value: LvefValue


class NyhaClassItem(_ItemBase):
    fact_type: Literal["nyha_class"]
    value: NyhaClassValue


class RestingHeartRateItem(_ItemBase):
    fact_type: Literal["resting_heart_rate"]
    value: RestingHeartRateValue


class BloodPressureItem(_ItemBase):
    fact_type: Literal["blood_pressure"]
    value: BloodPressureValue


class CardiacRhythmItem(_ItemBase):
    fact_type: Literal["cardiac_rhythm"]
    value: CardiacRhythmValue


class MedicationItem(_ItemBase):
    fact_type: Literal["medication"]
    value: MedicationValue


class BetaBlockerDoseStatusItem(_ItemBase):
    fact_type: Literal["beta_blocker_dose_status"]
    value: BetaBlockerDoseStatusValue


class ConditionHistoryItem(_ItemBase):
    fact_type: Literal["condition_history"]
    value: ConditionHistoryValue


class SymptomItem(_ItemBase):
    fact_type: Literal["symptom"]
    value: SymptomValue


ExtractedFactItem = Annotated[
    HfDiagnosisItem
    | LvefItem
    | NyhaClassItem
    | RestingHeartRateItem
    | BloodPressureItem
    | CardiacRhythmItem
    | MedicationItem
    | BetaBlockerDoseStatusItem
    | ConditionHistoryItem
    | SymptomItem,
    Field(discriminator="fact_type"),
]
ITEM_ADAPTER: TypeAdapter[Any] = TypeAdapter(ExtractedFactItem)


class ExtractionEnvelope(Strict):
    """Level-1 validation. `facts` items stay raw dicts here so one bad item
    cannot sink the whole run; each is validated with ITEM_ADAPTER."""

    schema_version: Literal["cardioflow.extraction.v1"]
    facts: list[dict[str, Any]] = Field(max_length=MAX_FACTS)


class _EnvelopeForSchema(Strict):
    """Used only to publish the JSON Schema to a model (tool input_schema)."""

    schema_version: Literal["cardioflow.extraction.v1"]
    facts: list[ExtractedFactItem] = Field(max_length=MAX_FACTS)


def extraction_json_schema() -> dict[str, Any]:
    return _EnvelopeForSchema.model_json_schema()
