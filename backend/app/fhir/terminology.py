"""Terminology table for the FHIR mapper.

POLICY: the mapper emits a `coding` entry ONLY when status == "verified".
Unverified entries render as CodeableConcept.text only. Every code below was
proposed from author knowledge and is UNVERIFIED until checked against the
source listed in this file. Verifying means looking it up,
confirm the display, set status="verified", fill verified_on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
UCUM = "http://unitsofmeasure.org"


@dataclass(frozen=True)
class Code:
    system: str
    code: str
    display: str
    status: Literal["verified", "unverified"]
    verify_at: str
    verified_on: str | None = None


# key → candidate code. Entries remain disabled until independently verified.
TERMS: dict[str, Code] = {
    # Observations (verify at https://loinc.org/search/)
    "obs.lvef": Code(LOINC, "10230-1", "Left ventricular Ejection fraction", "unverified", "loinc.org"),
    "obs.heart_rate": Code(LOINC, "8867-4", "Heart rate", "unverified", "loinc.org"),
    "obs.bp_panel": Code(
        LOINC, "85354-9", "Blood pressure panel with all children optional", "unverified", "loinc.org"
    ),
    "obs.bp_systolic": Code(LOINC, "8480-6", "Systolic blood pressure", "unverified", "loinc.org"),
    "obs.bp_diastolic": Code(LOINC, "8462-4", "Diastolic blood pressure", "unverified", "loinc.org"),
    "obs.nyha": Code(LOINC, "88020-3", "Functional capacity NYHA", "unverified", "loinc.org"),
    "obs.ecg_impression": Code(LOINC, "8601-7", "EKG impression", "unverified", "loinc.org"),
    # Conditions (SNOMED: https://browser.ihtsdotools.org ; ICD-10-CM: https://www.cms.gov/medicare/coding-billing/icd-10-codes)
    "cond.hfref": Code(
        SNOMED, "703272007", "Heart failure with reduced ejection fraction", "unverified", "SNOMED CT browser"
    ),
    "cond.hf_chronic_systolic.icd10": Code(
        ICD10CM, "I50.22", "Chronic systolic (congestive) heart failure", "unverified", "CMS ICD-10-CM"
    ),
    "cond.atrial_fibrillation": Code(SNOMED, "49436004", "Atrial fibrillation", "unverified", "SNOMED CT browser"),
    "finding.sinus_rhythm": Code(SNOMED, "426783006", "Sinus rhythm", "unverified", "SNOMED CT browser"),
    # Medications — ingredient-level RxNorm CUIs (verify at https://mor.nlm.nih.gov/RxNav/)
    # Intentionally left without codes until looked up; the mapper emits text only.
}

# Drug → TERMS key. Empty mapping by design until RxNorm codes are verified in RxNav.
RXNORM_INGREDIENT_KEY: dict[str, str] = {}
