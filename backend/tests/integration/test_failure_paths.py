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


def test_proposed_and_rejected_findings_do_not_satisfy_authorization(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "review-boundary.db")))
    view = create_and_extract(client, "hfref_golden")
    heart_rate = next(fact for fact in view["facts"] if fact["fact_type"] == "resting_heart_rate")

    proposed_result = next(
        requirement for requirement in view["prior_auth"]["requirements"] if requirement["requirement_id"] == "R7"
    )
    assert proposed_result["status"] == "MISSING"
    assert proposed_result["used_fact_ids"] == []
    assert proposed_result["pending_fact_ids"] == [heart_rate["id"]]

    response = client.post(
        f"/api/encounters/{view['encounter']['id']}/facts/{heart_rate['id']}/review",
        json={"expected_revision": view["encounter"]["revision"], "action": "approve"},
    )
    assert response.status_code == 200
    view = response.json()
    approved_result = next(
        requirement for requirement in view["prior_auth"]["requirements"] if requirement["requirement_id"] == "R7"
    )
    assert approved_result["status"] == "SATISFIED"
    assert approved_result["used_fact_ids"] == [heart_rate["id"]]

    response = client.post(
        f"/api/encounters/{view['encounter']['id']}/facts/{heart_rate['id']}/review",
        json={"expected_revision": view["encounter"]["revision"], "action": "reject"},
    )
    assert response.status_code == 200
    rejected_result = next(
        requirement
        for requirement in response.json()["prior_auth"]["requirements"]
        if requirement["requirement_id"] == "R7"
    )
    assert rejected_result["status"] == "MISSING"
    assert rejected_result["used_fact_ids"] == []


def test_simulated_gerd_uses_review_note_and_export_without_invented_policy(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "gerd.db")))
    view = create_and_extract(client, "gerd_simulated")

    assert view["fact_counts"]["total"] == 8
    assert view["fact_counts"]["pending_flagged"] == 0
    assert view["encounter"]["context"]["specialty"] == "gastroenterology"
    assert view["authorization_policy"] is None
    assert view["prior_auth"] is None

    for fact in list(view["facts"]):
        response = client.post(
            f"/api/encounters/{view['encounter']['id']}/facts/{fact['id']}/review",
            json={"expected_revision": view["encounter"]["revision"], "action": "approve"},
        )
        assert response.status_code == 200
        view = response.json()

    assert view["fact_counts"]["approved"] == 8
    audit = client.get(f"/api/encounters/{view['encounter']['id']}/audit").json()
    assert not any(event["type"] == "prior_auth.readiness_changed" for event in audit)
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


def test_reopen_removes_reviewed_value_from_downstream_state(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "reopen.db")))
    view = create_and_extract(client, "hfref_golden")
    heart_rate = next(fact for fact in view["facts"] if fact["fact_type"] == "resting_heart_rate")

    view = client.post(
        f"/api/encounters/{view['encounter']['id']}/facts/{heart_rate['id']}/review",
        json={"expected_revision": view["encounter"]["revision"], "action": "approve"},
    ).json()
    assert next(r for r in view["prior_auth"]["requirements"] if r["requirement_id"] == "R7")["status"] == "SATISFIED"

    view = client.post(
        f"/api/encounters/{view['encounter']['id']}/facts/{heart_rate['id']}/review",
        json={"expected_revision": view["encounter"]["revision"], "action": "reopen"},
    ).json()
    reopened = next(fact for fact in view["facts"] if fact["id"] == heart_rate["id"])
    result = next(r for r in view["prior_auth"]["requirements"] if r["requirement_id"] == "R7")
    assert reopened["review"]["status"] == "pending"
    assert reopened["approved"] is None
    assert result["status"] == "MISSING"
    assert result["used_fact_ids"] == []
    assert result["pending_fact_ids"] == [heart_rate["id"]]
