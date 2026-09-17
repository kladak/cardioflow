from datetime import UTC, date, datetime

from fhir.resources.R4B.bundle import Bundle

from app.domain.encounter import EncounterContext, SyntheticPatient
from app.domain.facts import ApprovedFact, Assertion, FactOrigin, FactType, parse_value
from app.fhir.mapper import build_bundle
from app.policy.engine import ApprovedFactRef

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def approved(
    fact_id: str,
    fact_type: FactType,
    raw: dict,
    assertion: Assertion = Assertion.AFFIRMED,
) -> ApprovedFactRef:
    return ApprovedFactRef(
        fact_id=fact_id,
        fact_type=fact_type,
        origin=FactOrigin.EXTRACTION,
        approved=ApprovedFact(
            value=parse_value(fact_type, raw),
            assertion=assertion,
            evidence=[],
            edited=False,
            approved_by="Dr. A. Reyes",
            approved_at=NOW,
        ),
    )


def test_fhir_represents_ranges_uncertainty_and_medication_units() -> None:
    facts = [
        approved(
            "fct_lvefrange01",
            FactType.LVEF,
            {"percent": 20, "percent_upper": 25, "measured_on_text": "June 12, 2026", "modality": "echocardiogram"},
        ),
        approved(
            "fct_history001",
            FactType.CONDITION_HISTORY,
            {"condition": "atrial_fibrillation", "timing_text": "many years ago"},
            Assertion.UNCERTAIN,
        ),
        approved(
            "fct_medication1",
            FactType.MEDICATION,
            {
                "drug": "other",
                "raw_name": "omeprazole",
                "dose_value": 20,
                "dose_unit": "mg",
                "frequency": "daily",
                "status": "active",
            },
        ),
    ]
    patient = SyntheticPatient(
        synthetic_mrn="SYN-999999",
        given_name="Test",
        family_name="Patient",
        birth_date=date(1970, 1, 1),
        administrative_gender="unknown",
        synthetic=True,
    )
    context = EncounterContext(
        encounter_date=date(2026, 9, 16),
        specialty="cardiology",
        visit_type="Synthetic review",
        clinician_display="Dr. A. Reyes",
        location_display="Demo clinic",
        fixture_id="hfref_golden",
    )

    bundle, _, _ = build_bundle(facts, patient, context, "enc_fhirtest001", "exp_fhirtest001", NOW)
    Bundle.model_validate(bundle)
    resources = [entry["resource"] for entry in bundle["entry"]]
    lvef = next(r for r in resources if r.get("code", {}).get("text") == "Left ventricular ejection fraction")
    history = next(r for r in resources if r["resourceType"] == "Condition")
    medication = next(r for r in resources if r["resourceType"] == "MedicationStatement")

    assert lvef["valueRange"]["low"]["value"] == 20
    assert lvef["valueRange"]["high"]["value"] == 25
    assert "valueQuantity" not in lvef
    assert history["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    assert history["note"] == [{"text": "many years ago"}]
    assert medication["dosage"][0]["text"] == "20.0 mg daily"
