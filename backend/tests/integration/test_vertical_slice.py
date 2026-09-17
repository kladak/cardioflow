from pathlib import Path

from fastapi.testclient import TestClient
from fhir.resources.R4B.bundle import Bundle

from app.core.settings import Settings
from app.main import create_app


def test_I_API_1_through_I_FHIR_2_golden_vertical_slice(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "cardioflow.db")))
    response = client.post("/api/encounters", json={"fixture_id": "hfref_golden"})
    assert response.status_code == 201
    view = response.json()
    encounter_id = view["encounter"]["id"]
    assert view["authorization_policy"]["id"] == "sim-ivabradine-hfref"
    assert len(view["authorization_policy"]["requirements"]) == 9

    response = client.post(
        f"/api/encounters/{encounter_id}/extraction-runs",
        json={"expected_revision": view["encounter"]["revision"]},
    )
    view = response.json()
    assert response.status_code == 200
    assert view["fact_counts"] == {
        "total": 18,
        "pending": 18,
        "pending_flagged": 1,
        "approved": 0,
        "approved_edited": 0,
        "rejected": 0,
    }
    for fact in list(view["facts"]):
        is_dizziness = fact["fact_type"] == "symptom" and fact["candidate"]["value"]["symptom"] == "dizziness"
        body = {"expected_revision": view["encounter"]["revision"], "action": "reject" if is_dizziness else "approve"}
        if is_dizziness:
            body["reason"] = "Single orthostatic episode, not clinically relevant"
        response = client.post(f"/api/encounters/{encounter_id}/facts/{fact['id']}/review", json=body)
        assert response.status_code == 200
        view = response.json()

    assert view["prior_auth"]["overall"] == "READY"
    heart_rate = next(f for f in view["facts"] if f["fact_type"] == "resting_heart_rate")
    heart_rate_result = next(r for r in view["prior_auth"]["requirements"] if r["requirement_id"] == "R7")
    heart_rate_rule = next(r for r in view["authorization_policy"]["requirements"] if r["id"] == "R7")
    assert heart_rate_result["used_fact_ids"] == [heart_rate["id"]]
    assert heart_rate["approved"]["evidence"]
    assert heart_rate_rule["criterion_sources"][0]["section"] == "1.1 Heart Failure in Adult Patients"
    original_evidence = heart_rate["candidate"]["evidence"]
    response = client.post(
        f"/api/encounters/{encounter_id}/facts/{heart_rate['id']}/review",
        json={"expected_revision": view["encounter"]["revision"], "action": "approve_with_edit", "value": {"bpm": 64}},
    )
    view = response.json()
    assert view["prior_auth"]["overall"] == "NOT_MET"
    assert next(r for r in view["prior_auth"]["requirements"] if r["requirement_id"] == "R7")["status"] == "NOT_MET"
    edited = next(f for f in view["facts"] if f["id"] == heart_rate["id"])
    assert edited["approved"]["evidence"] == original_evidence

    response = client.post(
        f"/api/encounters/{encounter_id}/facts/{heart_rate['id']}/review",
        json={"expected_revision": view["encounter"]["revision"], "action": "approve_with_edit", "value": {"bpm": 78}},
    )
    view = response.json()
    assert view["prior_auth"]["overall"] == "READY"
    response = client.post(
        f"/api/encounters/{encounter_id}/exports", json={"expected_revision": view["encounter"]["revision"]}
    )
    assert response.status_code == 201
    export = response.json()
    assert len(export["bundle"]["entry"]) == 15
    Bundle.model_validate(export["bundle"])
    approved_ids = {f["id"] for f in view["facts"] if f["review"]["status"] == "approved"}
    full_urls = {entry["fullUrl"] for entry in export["bundle"]["entry"]}
    for entry in export["bundle"]["entry"][2:]:
        assert entry["resource"]["identifier"][0]["value"] in approved_ids
    for entry in export["bundle"]["entry"]:
        resource = entry["resource"]
        for field in ("subject", "encounter", "context"):
            if field in resource:
                assert resource[field]["reference"] in full_urls
    exported_fact_ids = {fact_id for item in export["manifest"] for fact_id in item["fact_ids"]}
    excluded_fact_ids = {item["fact_id"] for item in export["excluded"]}
    assert exported_fact_ids | excluded_fact_ids == approved_ids
