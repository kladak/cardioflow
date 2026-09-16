from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from fhir.resources.R4B.bundle import Bundle

from app.core.settings import Settings
from app.main import create_app


def create_and_extract(client: TestClient, fixture_id: str) -> dict:
    created = client.post("/api/encounters", json={"fixture_id": fixture_id})
    assert created.status_code == 201
    view = created.json()
    extracted = client.post(
        f"/api/encounters/{view['encounter']['id']}/extraction-runs",
        json={"expected_revision": view["encounter"]["revision"]},
    )
    assert extracted.status_code == 200
    return extracted.json()


def test_adversarial_fixture_remains_flagged_and_incomplete(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "adversarial.db")))
    view = create_and_extract(client, "hfref_ambiguous")

    assert view["extraction"]["latest_run"]["status"] == "succeeded"
    assert view["fact_counts"] == {
        "total": 9,
        "pending": 9,
        "pending_flagged": 6,
        "approved": 0,
        "approved_edited": 0,
        "rejected": 0,
    }
    assert view["prior_auth"]["overall"] == "INCOMPLETE"
    extracted_types = {fact["fact_type"] for fact in view["facts"]}
    assert extracted_types.isdisjoint(
        {"nyha_class", "cardiac_rhythm", "hf_diagnosis", "beta_blocker_dose_status"}
    )
    assert view["export"]["can_export"] is False


def test_invalid_json_fails_safely_without_proposed_state(tmp_path: Path) -> None:
    settings = Settings(db_path=tmp_path / "invalid-json.db", mock_scenario="invalid_json")
    client = TestClient(create_app(settings))
    view = create_and_extract(client, "hfref_golden")

    run = view["extraction"]["latest_run"]
    assert run["status"] == "failed"
    assert [issue["kind"] for issue in run["issues"]] == ["invalid_json"]
    assert view["facts"] == []
    assert view["prior_auth"]["overall"] == "INCOMPLETE"
    assert view["export"]["can_export"] is False


def test_simulated_gerd_uses_review_note_and_export_without_invented_policy(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "gerd.db")))
    view = create_and_extract(client, "gerd_simulated")

    assert view["fact_counts"]["total"] == 8
    assert view["fact_counts"]["pending_flagged"] == 0
    assert view["encounter"]["context"]["specialty"] == "gastroenterology"

    for fact in list(view["facts"]):
        response = client.post(
            f"/api/encounters/{view['encounter']['id']}/facts/{fact['id']}/review",
            json={"expected_revision": view["encounter"]["revision"], "action": "approve"},
        )
        assert response.status_code == 200
        view = response.json()

    assert view["fact_counts"]["approved"] == 8
    note = "\n".join(section["effective_text"] for section in view["note_sections"])
    assert "gastroesophageal reflux disease" in note
    assert "omeprazole 20 milligrams daily" in note

    response = client.post(
        f"/api/encounters/{view['encounter']['id']}/exports",
        json={"expected_revision": view["encounter"]["revision"]},
    )
    assert response.status_code == 201
    export = response.json()
    encounter = next(
        entry["resource"]
        for entry in export["bundle"]["entry"]
        if entry["resource"]["resourceType"] == "Encounter"
    )
    assert encounter["serviceType"]["text"] == "Gastroenterology"
    assert len(export["excluded"]) == 6
    Bundle.model_validate(export["bundle"])
