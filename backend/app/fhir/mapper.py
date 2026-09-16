# mypy: disable-error-code=union-attr
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from app.domain.encounter import EncounterContext, ExportExclusion, ExportManifestEntry, SyntheticPatient
from app.domain.facts import Assertion, FactType
from app.policy.dates import resolve_spoken_date
from app.policy.engine import ApprovedFactRef

NS = uuid.UUID("d93338f6-5dcb-4e8f-9c97-ea811d3109cd")


def build_bundle(
    approved: list[ApprovedFactRef],
    patient: SyntheticPatient,
    context: EncounterContext,
    encounter_id: str,
    export_id: str,
    generated_at: datetime,
) -> tuple[dict[str, Any], list[ExportManifestEntry], list[ExportExclusion]]:
    pid = str(uuid.uuid5(NS, f"{encounter_id}:patient"))
    eid = str(uuid.uuid5(NS, f"{encounter_id}:encounter"))
    entries = [
        {
            "fullUrl": f"urn:uuid:{pid}",
            "resource": {
                "resourceType": "Patient",
                "id": pid,
                "meta": {"tag": [{"system": "urn:cardioflow", "code": "synthetic"}]},
                "identifier": [{"system": "urn:cardioflow:synthetic-mrn", "value": patient.synthetic_mrn}],
                "name": [{"family": patient.family_name, "given": [patient.given_name]}],
                "gender": patient.administrative_gender,
                "birthDate": patient.birth_date.isoformat(),
            },
        },
        {
            "fullUrl": f"urn:uuid:{eid}",
            "resource": {
                "resourceType": "Encounter",
                "id": eid,
                "status": "finished",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
                "type": [{"text": context.visit_type}],
                "serviceType": {"text": context.specialty.replace("_", " ").title()},
                "subject": {"reference": f"urn:uuid:{pid}"},
                "period": {"start": context.encounter_date.isoformat()},
                "participant": [{"individual": {"display": context.clinician_display}}],
            },
        },
    ]
    manifest = [
        ExportManifestEntry(resource_type="Patient", resource_id=f"urn:uuid:{pid}", fact_ids=[]),
        ExportManifestEntry(resource_type="Encounter", resource_id=f"urn:uuid:{eid}", fact_ids=[]),
    ]
    excluded = []
    for f in approved:
        v = f.approved.value
        r: dict[str, Any] | None = None
        base: dict[str, Any] = {
            "identifier": [{"system": "urn:cardioflow:fact", "value": f.fact_id}],
            "subject": {"reference": f"urn:uuid:{pid}"},
            "encounter": {"reference": f"urn:uuid:{eid}"},
        }
        if f.fact_type is FactType.HF_DIAGNOSIS:
            r = {
                "resourceType": "Condition",
                "clinicalStatus": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
                },
                "verificationStatus": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                            "code": "confirmed" if f.approved.assertion is Assertion.AFFIRMED else "provisional",
                        }
                    ]
                },
                "code": {"text": "Chronic heart failure with reduced ejection fraction"},
                **base,
            }
        elif f.fact_type is FactType.CONDITION_HISTORY:
            code = "refuted" if f.approved.assertion is Assertion.NEGATED else "confirmed"
            r = {
                "resourceType": "Condition",
                "verificationStatus": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": code}]
                },
                "code": {"text": v.condition.replace("_", " ")},
                **base,
            }
        elif f.fact_type in {
            FactType.LVEF,
            FactType.RESTING_HEART_RATE,
            FactType.BLOOD_PRESSURE,
            FactType.NYHA_CLASS,
            FactType.CARDIAC_RHYTHM,
        }:
            label = {
                FactType.LVEF: "Left ventricular ejection fraction",
                FactType.RESTING_HEART_RATE: "Resting heart rate",
                FactType.BLOOD_PRESSURE: "Blood pressure",
                FactType.NYHA_CLASS: "NYHA class",
                FactType.CARDIAC_RHYTHM: "Cardiac rhythm",
            }[f.fact_type]
            r = {
                "resourceType": "Observation",
                "status": "final" if f.approved.assertion is Assertion.AFFIRMED else "preliminary",
                "code": {"text": label},
                **base,
            }
            if f.fact_type is FactType.LVEF:
                r["valueQuantity"] = {
                    "value": v.percent,
                    "unit": "%",
                    "system": "http://unitsofmeasure.org",
                    "code": "%",
                }
                resolved = resolve_spoken_date(v.measured_on_text, context.encounter_date)
                if resolved:
                    r["effectiveDateTime"] = resolved.isoformat()
            elif f.fact_type is FactType.RESTING_HEART_RATE:
                r["valueQuantity"] = {
                    "value": v.bpm,
                    "unit": "beats/minute",
                    "system": "http://unitsofmeasure.org",
                    "code": "/min",
                }
            elif f.fact_type is FactType.BLOOD_PRESSURE:
                r["component"] = [
                    {"code": {"text": "Systolic"}, "valueQuantity": {"value": v.systolic, "unit": "mmHg"}},
                    {"code": {"text": "Diastolic"}, "valueQuantity": {"value": v.diastolic, "unit": "mmHg"}},
                ]
            elif f.fact_type is FactType.NYHA_CLASS:
                r["valueCodeableConcept"] = {"text": f"NYHA class {v.nyha}"}
            else:
                r["valueCodeableConcept"] = {"text": v.rhythm.replace("_", " ")}
        elif f.fact_type is FactType.MEDICATION:
            if f.approved.assertion is Assertion.HYPOTHETICAL:
                excluded.append(ExportExclusion(fact_id=f.fact_id, reason="hypothetical medication is not exported"))
                continue
            typ = "MedicationRequest" if v.status == "planned" else "MedicationStatement"
            r = {
                "resourceType": typ,
                "status": "draft"
                if typ == "MedicationRequest"
                else {"active": "active", "held": "on-hold", "discontinued": "stopped"}.get(v.status, "unknown"),
                "medicationCodeableConcept": {"text": v.raw_name},
                **base,
            }
            if typ == "MedicationStatement":
                r["context"] = r.pop("encounter")
            dose = " ".join(x for x in [v.dose_text or (str(v.dose_value) if v.dose_value else ""), v.frequency] if x)
            r["intent"] = "plan" if typ == "MedicationRequest" else None
            r["dosageInstruction" if typ == "MedicationRequest" else "dosage"] = [{"text": dose}]
            r = {k: v2 for k, v2 in r.items() if v2 is not None}
        else:
            excluded.append(
                ExportExclusion(fact_id=f.fact_id, reason="not mapped in v1; represented in the clinical note")
            )
            continue
        rid = str(uuid.uuid5(NS, f"{encounter_id}:{f.fact_id}"))
        r["id"] = rid
        full = f"urn:uuid:{rid}"
        entries.append({"fullUrl": full, "resource": r})
        manifest.append(ExportManifestEntry(resource_type=r["resourceType"], resource_id=full, fact_ids=[f.fact_id]))
    bundle = {
        "resourceType": "Bundle",
        # FHIR ids exclude underscores; keep the CardioFlow export id in the manifest/API,
        # while using its standards-safe equivalent inside the Bundle resource.
        "id": export_id.replace("_", "-"),
        "type": "collection",
        "timestamp": generated_at.isoformat(),
        "entry": entries,
    }
    return bundle, manifest, excluded


def resource_counts(bundle: dict[str, Any]) -> dict[str, int]:
    return dict(Counter(e["resource"]["resourceType"] for e in bundle["entry"]))
