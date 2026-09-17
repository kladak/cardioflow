"""Foundation contract tests. These exist BEFORE the implementation and must keep passing.
They prove the fixtures, schemas and policy are mutually consistent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.encounter import Encounter, EncounterContext, SyntheticPatient, Transcript
from app.domain.facts import ALLOWED_ASSERTIONS, Assertion, FactType, parse_value
from app.domain.policy import AuthorizationPolicy, ProvenanceClassification
from app.extraction.contract import ITEM_ADAPTER, ExtractionEnvelope, extraction_json_schema

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
EXPECTED = json.loads((FIX / "extraction" / "expected_outcomes.json").read_text())


def load_encounter_fixture(fid: str) -> dict:
    return json.loads((FIX / "encounters" / f"{fid}.json").read_text())


@pytest.mark.parametrize("fid", ["hfref_golden", "hfref_ambiguous", "gerd_simulated"])
def test_encounter_fixture_parses(fid: str) -> None:
    raw = load_encounter_fixture(fid)
    SyntheticPatient.model_validate(raw["patient"])
    EncounterContext.model_validate(raw["context"])
    Transcript.model_validate({"segments": raw["segments"]})


@pytest.mark.parametrize("fid", ["hfref_golden", "hfref_ambiguous", "gerd_simulated"])
def test_default_mock_output_is_fully_valid_and_verbatim(fid: str) -> None:
    raw = load_encounter_fixture(fid)
    seg = {s["id"]: s["text"] for s in raw["segments"]}
    env = ExtractionEnvelope.model_validate_json((FIX / "extraction" / f"{fid}.default.json").read_text())
    assert env.facts, "default mock output must propose facts"
    for item in env.facts:
        parsed = ITEM_ADAPTER.validate_python(item)
        assert parsed.assertion in ALLOWED_ASSERTIONS[FactType(parsed.fact_type)]
        for ev in parsed.evidence:
            # default fixtures are exact-substring clean (no normalization needed)
            assert ev.quote in seg[ev.segment_id], (parsed.fact_type, ev.segment_id, ev.quote)
    counts: dict[str, int] = {}
    for item in env.facts:
        counts[item["fact_type"]] = counts.get(item["fact_type"], 0) + 1
    assert counts == EXPECTED[fid]["default"]["accepted_by_type"]


def test_ambiguous_mock_does_not_invent_unstated_facts() -> None:
    env = json.loads((FIX / "extraction" / "hfref_ambiguous.default.json").read_text())
    types = {f["fact_type"] for f in env["facts"]}
    for forbidden in ("nyha_class", "cardiac_rhythm", "hf_diagnosis", "beta_blocker_dose_status"):
        assert forbidden not in types


def test_invalid_json_fixture_is_not_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        json.loads((FIX / "extraction" / "hfref_golden.invalid_json.txt").read_text())


def test_envelope_invalid_fixture_fails_envelope() -> None:
    with pytest.raises(ValidationError):
        ExtractionEnvelope.model_validate_json((FIX / "extraction" / "hfref_golden.envelope_invalid.json").read_text())


def test_item_errors_fixture_item_level_outcomes() -> None:
    env = ExtractionEnvelope.model_validate_json((FIX / "extraction" / "hfref_golden.item_errors.json").read_text())
    schema_ok = []
    for item in env.facts:
        try:
            schema_ok.append(ITEM_ADAPTER.validate_python(item))
        except ValidationError:
            pass
    assert len(schema_ok) == 2  # valid lvef + negated lvef (schema-valid, assertion disallowed later)
    disallowed = [i for i in schema_ok if i.assertion not in ALLOWED_ASSERTIONS[FactType(i.fact_type)]]
    assert len(disallowed) == 1 and disallowed[0].assertion is Assertion.NEGATED


def test_value_models_reject_invented_shapes() -> None:
    with pytest.raises(ValidationError):
        parse_value(FactType.LVEF, {"percent": 30, "percent_upper": 25, "modality": "echocardiogram"})
    with pytest.raises(ValidationError):
        parse_value(FactType.BLOOD_PRESSURE, {"systolic": 70, "diastolic": 112})
    with pytest.raises(ValidationError):
        parse_value(FactType.NYHA_CLASS, {"nyha": "3"})


def test_policy_loads_and_is_simulated() -> None:
    p = AuthorizationPolicy.model_validate_json((ROOT / "app/policy/policies/sim_ivabradine_hfref_v1.json").read_text())
    assert p.simulated is True
    assert [r.id for r in p.requirements] == [f"R{i}" for i in range(1, 10)]
    bad = json.loads((ROOT / "app/policy/policies/sim_ivabradine_hfref_v1.json").read_text()) | {"simulated": False}
    with pytest.raises(ValidationError):
        AuthorizationPolicy.model_validate(bad)


def test_every_policy_requirement_has_explicit_provenance() -> None:
    raw = json.loads((ROOT / "app/policy/policies/sim_ivabradine_hfref_v1.json").read_text())
    policy = AuthorizationPolicy.model_validate(raw)
    classifications = {requirement.id: requirement.provenance_classification for requirement in policy.requirements}

    assert classifications == {
        "R1": ProvenanceClassification.DEMO_RULE,
        "R2": ProvenanceClassification.DEMO_RULE,
        "R3": ProvenanceClassification.SUPPORTED,
        "R4": ProvenanceClassification.DEMO_RULE,
        "R5": ProvenanceClassification.SUPPORTED,
        "R6": ProvenanceClassification.DEMO_RULE,
        "R7": ProvenanceClassification.SUPPORTED,
        "R8": ProvenanceClassification.SUPPORTED,
        "R9": ProvenanceClassification.DEMO_RULE,
    }
    assert not any(value is ProvenanceClassification.PAYER_SPECIFIC for value in classifications.values())
    requirements = {requirement.id: requirement for requirement in policy.requirements}
    assert requirements["R8"].params["accepted"] == ["at_max_tolerated_dose", "contraindicated"]
    assert len(requirements["R9"].criterion_sources) == 2
    for requirement in policy.requirements:
        assert requirement.operator
        assert requirement.provenance_note
        assert requirement.last_verified_at.isoformat() == "2026-09-16"
        if requirement.provenance_classification is ProvenanceClassification.SUPPORTED:
            assert requirement.criterion_sources
            for source in requirement.criterion_sources:
                assert source.title
                assert source.organization
                assert source.url.startswith("https://")
                assert source.section
                assert source.version_or_date


def test_supported_policy_requirement_cannot_omit_authoritative_source() -> None:
    raw = json.loads((ROOT / "app/policy/policies/sim_ivabradine_hfref_v1.json").read_text())
    raw["requirements"][2]["criterion_sources"] = []
    with pytest.raises(ValidationError):
        AuthorizationPolicy.model_validate(raw)


def test_expected_requirement_ids_match_policy() -> None:
    for fid in ("hfref_golden", "hfref_ambiguous"):
        exp = EXPECTED[fid]["default"]["requirements_after_approve_all"]
        assert sorted(exp) == sorted(f"R{i}" for i in range(1, 10))


def test_json_schema_publishes() -> None:
    s = extraction_json_schema()
    assert s["properties"]["schema_version"]["const"] == "cardioflow.extraction.v1"


def test_empty_encounter_aggregate_constructs() -> None:
    raw = load_encounter_fixture("hfref_golden")
    Encounter.model_validate(
        {
            "id": "enc_0123456789",
            "created_at": "2026-08-04T15:00:00Z",
            "updated_at": "2026-08-04T15:00:00Z",
            "revision": 0,
            "review_revision": 0,
            "patient": raw["patient"],
            "context": raw["context"],
            "transcript": {"segments": raw["segments"]},
        }
    )


def test_hypothetical_only_for_planned_medication() -> None:
    from app.domain.facts import MedicationValue, assertion_allowed

    base = {"drug": "carvedilol", "raw_name": "carvedilol", "frequency": "unspecified"}
    active = MedicationValue.model_validate(base | {"status": "active"})
    planned = MedicationValue.model_validate(base | {"status": "planned"})
    assert not assertion_allowed(FactType.MEDICATION, active, Assertion.HYPOTHETICAL)
    assert assertion_allowed(FactType.MEDICATION, planned, Assertion.HYPOTHETICAL)
