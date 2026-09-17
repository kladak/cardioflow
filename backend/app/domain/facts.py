"""Clinical fact domain: the closed catalog of fact types CardioFlow understands,
their typed values, provenance spans, and the candidate-vs-approved split.

AUTHORITATIVE. The extraction contract, rule engine, note generator and FHIR mapper
all depend on these types. Change them deliberately and update ARCHITECTURE.md §3.2.

Key invariant: *nothing downstream of review (rules, note, FHIR) may read
`Fact.candidate`*. Downstream code reads `Fact.approved` only. See
`approved_facts()` in services is the single gate.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- enums
class Speaker(StrEnum):
    CLINICIAN = "clinician"
    PATIENT = "patient"
    STAFF = "staff"  # MA / nurse reading vitals
    OTHER = "other"  # family member, interpreter


class FactType(StrEnum):
    HF_DIAGNOSIS = "hf_diagnosis"
    LVEF = "lvef"
    NYHA_CLASS = "nyha_class"
    RESTING_HEART_RATE = "resting_heart_rate"
    BLOOD_PRESSURE = "blood_pressure"
    CARDIAC_RHYTHM = "cardiac_rhythm"
    MEDICATION = "medication"
    BETA_BLOCKER_DOSE_STATUS = "beta_blocker_dose_status"
    CONDITION_HISTORY = "condition_history"
    SYMPTOM = "symptom"


# At most one APPROVED fact of these types per encounter (enforced at review time → 409).
SINGLE_VALUED_TYPES: frozenset[FactType] = frozenset(
    {
        FactType.HF_DIAGNOSIS,
        FactType.LVEF,
        FactType.NYHA_CLASS,
        FactType.RESTING_HEART_RATE,
        FactType.BLOOD_PRESSURE,
        FactType.CARDIAC_RHYTHM,
        FactType.BETA_BLOCKER_DOSE_STATUS,
    }
)

# Types that represent a measurement/test result. If every evidence span for such a
# fact is spoken by the PATIENT, the fact is flagged PATIENT_REPORTED_MEASUREMENT.
MEASUREMENT_TYPES: frozenset[FactType] = frozenset(
    {FactType.LVEF, FactType.RESTING_HEART_RATE, FactType.BLOOD_PRESSURE, FactType.CARDIAC_RHYTHM}
)


class Assertion(StrEnum):
    AFFIRMED = "affirmed"  # stated as true
    NEGATED = "negated"  # explicitly stated as absent ("no, never had AFib")
    UNCERTAIN = "uncertain"  # hedged ("I think it was 20, maybe 25")
    HYPOTHETICAL = "hypothetical"  # considered but not decided ("might consider X down the road")


ALLOWED_ASSERTIONS: dict[FactType, frozenset[Assertion]] = {
    FactType.HF_DIAGNOSIS: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.LVEF: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.NYHA_CLASS: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.RESTING_HEART_RATE: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.BLOOD_PRESSURE: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.CARDIAC_RHYTHM: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.MEDICATION: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN, Assertion.HYPOTHETICAL}),
    FactType.BETA_BLOCKER_DOSE_STATUS: frozenset({Assertion.AFFIRMED, Assertion.UNCERTAIN}),
    FactType.CONDITION_HISTORY: frozenset({Assertion.AFFIRMED, Assertion.NEGATED, Assertion.UNCERTAIN}),
    FactType.SYMPTOM: frozenset({Assertion.AFFIRMED, Assertion.NEGATED, Assertion.UNCERTAIN}),
}


class ModelConfidence(StrEnum):
    """Self-reported by the model. Poorly calibrated: used ONLY to raise a review flag,
    never to auto-approve and never by the rule engine."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewFlag(StrEnum):
    """Computed deterministically at ingest (see ARCHITECTURE.md §5.4). Flags draw the
    clinician's attention; they never change a fact's value or status."""

    MODEL_LOW_CONFIDENCE = "model_low_confidence"
    VALUE_NOT_IN_EVIDENCE = "value_not_in_evidence"
    HEDGED_LANGUAGE = "hedged_language"
    PATIENT_REPORTED_MEASUREMENT = "patient_reported_measurement"
    CONFLICTING_CANDIDATES = "conflicting_candidates"
    UNCERTAIN_OR_HYPOTHETICAL = "uncertain_or_hypothetical"
    EVIDENCE_IS_QUESTION = "evidence_is_question"


# --------------------------------------------------------------------------- drugs
class Drug(StrEnum):
    METOPROLOL_SUCCINATE = "metoprolol_succinate"
    CARVEDILOL = "carvedilol"
    BISOPROLOL = "bisoprolol"
    SACUBITRIL_VALSARTAN = "sacubitril_valsartan"
    LISINOPRIL = "lisinopril"
    LOSARTAN = "losartan"
    VALSARTAN = "valsartan"
    SPIRONOLACTONE = "spironolactone"
    EPLERENONE = "eplerenone"
    DAPAGLIFLOZIN = "dapagliflozin"
    EMPAGLIFLOZIN = "empagliflozin"
    FUROSEMIDE = "furosemide"
    TORSEMIDE = "torsemide"
    BUMETANIDE = "bumetanide"
    IVABRADINE = "ivabradine"
    DIGOXIN = "digoxin"
    OTHER = "other"  # unnamed or out-of-catalog drug; raw_name carries the text


class DrugClass(StrEnum):
    BETA_BLOCKER = "beta_blocker"
    ARNI = "arni"
    ACE_INHIBITOR = "ace_inhibitor"
    ARB = "arb"
    MRA = "mra"
    SGLT2_INHIBITOR = "sglt2_inhibitor"
    LOOP_DIURETIC = "loop_diuretic"
    HCN_BLOCKER = "hcn_channel_blocker"
    CARDIAC_GLYCOSIDE = "cardiac_glycoside"
    UNKNOWN = "unknown"


DRUG_CLASS: dict[Drug, DrugClass] = {
    Drug.METOPROLOL_SUCCINATE: DrugClass.BETA_BLOCKER,
    Drug.CARVEDILOL: DrugClass.BETA_BLOCKER,
    Drug.BISOPROLOL: DrugClass.BETA_BLOCKER,
    Drug.SACUBITRIL_VALSARTAN: DrugClass.ARNI,
    Drug.LISINOPRIL: DrugClass.ACE_INHIBITOR,
    Drug.LOSARTAN: DrugClass.ARB,
    Drug.VALSARTAN: DrugClass.ARB,
    Drug.SPIRONOLACTONE: DrugClass.MRA,
    Drug.EPLERENONE: DrugClass.MRA,
    Drug.DAPAGLIFLOZIN: DrugClass.SGLT2_INHIBITOR,
    Drug.EMPAGLIFLOZIN: DrugClass.SGLT2_INHIBITOR,
    Drug.FUROSEMIDE: DrugClass.LOOP_DIURETIC,
    Drug.TORSEMIDE: DrugClass.LOOP_DIURETIC,
    Drug.BUMETANIDE: DrugClass.LOOP_DIURETIC,
    Drug.IVABRADINE: DrugClass.HCN_BLOCKER,
    Drug.DIGOXIN: DrugClass.CARDIAC_GLYCOSIDE,
    Drug.OTHER: DrugClass.UNKNOWN,
}


# --------------------------------------------------------------------------- values
# Rule for every value model: a field the transcript does not state is null /
# "unspecified". Never a default that looks like data.

NyhaRoman = Literal["I", "II", "III", "IV"]
_NYHA_ORDER = {"I": 1, "II": 2, "III": 3, "IV": 4}


class HfDiagnosisValue(Strict):
    hf_type: Literal["hfref", "hfmref", "hfpef", "unspecified"]
    chronicity: Literal["chronic", "acute", "acute_on_chronic", "unspecified"]


class LvefValue(Strict):
    percent: int = Field(ge=5, le=85, description="Point value, or lower bound of a stated range")
    percent_upper: int | None = Field(default=None, ge=5, le=85, description="Only when a range was stated")
    measured_on_text: str | None = Field(
        default=None, max_length=60, description="Date exactly as spoken ('June 12th'). Resolved deterministically."
    )
    modality: Literal["echocardiogram", "cardiac_mri", "nuclear", "other", "unspecified"]

    @model_validator(mode="after")
    def _range(self) -> LvefValue:
        if self.percent_upper is not None and self.percent_upper <= self.percent:
            raise ValueError("percent_upper must be greater than percent")
        return self


class NyhaClassValue(Strict):
    nyha: NyhaRoman
    nyha_upper: NyhaRoman | None = Field(default=None, description="Only when a range like 'II to III' was stated")

    @model_validator(mode="after")
    def _range(self) -> NyhaClassValue:
        if self.nyha_upper is not None and _NYHA_ORDER[self.nyha_upper] <= _NYHA_ORDER[self.nyha]:
            raise ValueError("nyha_upper must be higher than nyha")
        return self


class RestingHeartRateValue(Strict):
    bpm: int = Field(ge=20, le=250)


class BloodPressureValue(Strict):
    systolic: int = Field(ge=50, le=260)
    diastolic: int = Field(ge=20, le=160)

    @model_validator(mode="after")
    def _order(self) -> BloodPressureValue:
        if self.diastolic >= self.systolic:
            raise ValueError("diastolic must be lower than systolic")
        return self


class CardiacRhythmValue(Strict):
    rhythm: Literal["sinus", "atrial_fibrillation", "atrial_flutter", "paced", "other"]
    source: Literal["ecg", "monitor", "exam", "unspecified"]


class MedicationValue(Strict):
    drug: Drug
    raw_name: str = Field(min_length=1, max_length=80, description="Name as spoken, e.g. 'Farxiga'")
    dose_value: float | None = Field(default=None, gt=0)
    dose_unit: Literal["mg", "mcg"] | None = Field(default=None, description="Null unless the unit was stated")
    dose_text: str | None = Field(default=None, max_length=40, description="Dose as spoken, e.g. '49/51'")
    frequency: Literal["daily", "bid", "tid", "qhs", "prn", "other", "unspecified"]
    status: Literal["active", "planned", "discontinued", "held"]
    adherence_note: str | None = Field(default=None, max_length=200)


class BetaBlockerDoseStatusValue(Strict):
    status: Literal["at_max_tolerated_dose", "below_max_tolerated_dose", "contraindicated", "not_tolerated"]


class ConditionHistoryValue(Strict):
    condition: Literal[
        "atrial_fibrillation",
        "atrial_flutter",
        "sick_sinus_syndrome",
        "third_degree_av_block",
        "permanent_pacemaker",
        "gastroesophageal_reflux_disease",
    ]
    timing_text: str | None = Field(default=None, max_length=60)


class SymptomValue(Strict):
    symptom: Literal[
        "dyspnea_on_exertion",
        "orthopnea",
        "paroxysmal_nocturnal_dyspnea",
        "peripheral_edema",
        "fatigue",
        "dizziness",
        "palpitations",
        "chest_pain",
        "heartburn",
        "acid_regurgitation",
        "dysphagia",
        "melena",
        "hematemesis",
        "unintentional_weight_loss",
    ]
    detail_text: str | None = Field(default=None, max_length=120)


FactValue = (
    HfDiagnosisValue
    | LvefValue
    | NyhaClassValue
    | RestingHeartRateValue
    | BloodPressureValue
    | CardiacRhythmValue
    | MedicationValue
    | BetaBlockerDoseStatusValue
    | ConditionHistoryValue
    | SymptomValue
)

VALUE_MODEL: dict[FactType, type[Strict]] = {
    FactType.HF_DIAGNOSIS: HfDiagnosisValue,
    FactType.LVEF: LvefValue,
    FactType.NYHA_CLASS: NyhaClassValue,
    FactType.RESTING_HEART_RATE: RestingHeartRateValue,
    FactType.BLOOD_PRESSURE: BloodPressureValue,
    FactType.CARDIAC_RHYTHM: CardiacRhythmValue,
    FactType.MEDICATION: MedicationValue,
    FactType.BETA_BLOCKER_DOSE_STATUS: BetaBlockerDoseStatusValue,
    FactType.CONDITION_HISTORY: ConditionHistoryValue,
    FactType.SYMPTOM: SymptomValue,
}

# Numeric value fields checked against evidence text for VALUE_NOT_IN_EVIDENCE.
NUMERIC_GROUNDING_FIELDS: dict[FactType, tuple[str, ...]] = {
    FactType.LVEF: ("percent", "percent_upper"),
    FactType.RESTING_HEART_RATE: ("bpm",),
    FactType.BLOOD_PRESSURE: ("systolic", "diastolic"),
    FactType.MEDICATION: ("dose_value",),
}


def assertion_allowed(fact_type: FactType, value: Strict, assertion: Assertion) -> bool:
    """Type-level allowed set plus one value-dependent rule: a medication can be
    `hypothetical` only when its status is `planned` (you can't 'maybe be taking' via hypothetical;
    use `uncertain`). Used by the pipeline (DISALLOWED_ASSERTION), review validation, and Fact invariants."""
    if assertion not in ALLOWED_ASSERTIONS[fact_type]:
        return False
    if fact_type is FactType.MEDICATION and assertion is Assertion.HYPOTHETICAL:
        return isinstance(value, MedicationValue) and value.status == "planned"
    return True


def parse_value(fact_type: FactType, raw: object) -> Strict:
    """The ONLY way to turn untrusted input into a fact value."""
    return VALUE_MODEL[fact_type].model_validate(raw)


# --------------------------------------------------------------------------- provenance
class EvidenceSpan(Strict):
    """A verbatim, server-verified slice of one transcript segment.
    Invariant (checked by grounding): segment.text[char_start:char_end] == quote."""

    segment_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    speaker: Speaker  # denormalized from the segment for display and rules

    @model_validator(mode="after")
    def _bounds(self) -> EvidenceSpan:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be > char_start")
        if self.char_end - self.char_start != len(self.quote):
            raise ValueError("span length must equal quote length")
        return self


# --------------------------------------------------------------------------- facts
class FactOrigin(StrEnum):
    EXTRACTION = "extraction"  # proposed by an extraction run
    CLINICIAN = "clinician"  # entered by the clinician (e.g. from the chart) to resolve a gap


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CandidateFact(Strict):
    """Immutable extraction proposal. Written once at ingest; never mutated by review."""

    value: FactValue
    assertion: Assertion
    evidence: list[EvidenceSpan] = Field(min_length=1)
    model_confidence: ModelConfidence
    rationale: str | None = Field(default=None, max_length=280)  # display only; never parsed
    flags: list[ReviewFlag] = Field(default_factory=list)


class ApprovedFact(Strict):
    """Clinician-attested state. The only fact state rules, note and FHIR may read."""

    value: FactValue
    assertion: Assertion
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # copied from candidate; [] for clinician-origin
    edited: bool  # True when value or assertion differs from the candidate
    attestation_note: str | None = Field(default=None, max_length=280)  # required for clinician-origin facts
    approved_by: str
    approved_at: datetime


class ReviewState(Strict):
    status: ReviewStatus
    decided_by: str | None = None
    decided_at: datetime | None = None
    rejection_reason: str | None = Field(default=None, max_length=280)


class Fact(Strict):
    id: str = Field(pattern=r"^fct_[a-z0-9]{10,}$")
    fact_type: FactType
    origin: FactOrigin
    extraction_run_id: str | None = None
    candidate: CandidateFact | None = None
    review: ReviewState
    approved: ApprovedFact | None = None

    @model_validator(mode="after")
    def _invariants(self) -> Fact:
        model = VALUE_MODEL[self.fact_type]
        if self.origin is FactOrigin.EXTRACTION:
            if self.candidate is None or self.extraction_run_id is None:
                raise ValueError("extraction-origin fact requires candidate and extraction_run_id")
        else:
            if self.candidate is not None:
                raise ValueError("clinician-origin fact has no candidate")
            if self.review.status is not ReviewStatus.APPROVED or self.approved is None:
                raise ValueError("clinician-origin fact is approved at creation")
            if not self.approved.attestation_note:
                raise ValueError("clinician-origin fact requires attestation_note")
        for state in (self.candidate, self.approved):
            if state is None:
                continue
            if not isinstance(state.value, model):
                raise ValueError(f"value for {self.fact_type} must be {model.__name__}")
            if not assertion_allowed(self.fact_type, state.value, state.assertion):
                raise ValueError(f"assertion {state.assertion} not allowed for this {self.fact_type} value")
        if (self.review.status is ReviewStatus.APPROVED) != (self.approved is not None):
            raise ValueError("approved state present iff review.status == approved")
        return self
