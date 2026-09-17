from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.api.schemas import CreateEncounterRequest
from app.core.clock import SystemClock
from app.core.ids import new_id
from app.extraction.providers.mock import MockProvider
from app.services.encounter_service import EncounterService
from app.store.sqlite import SQLiteStore


def test_audit_rows_cannot_be_updated_or_deleted(tmp_path: Path) -> None:
    path = tmp_path / "append-only.db"
    store = SQLiteStore(path)
    service = EncounterService(store, MockProvider(), SystemClock(), new_id, "Dr. A. Reyes")
    view = service.create(CreateEncounterRequest(fixture_id="hfref_golden"))
    encounter_id = view.encounter.id

    with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE audit_events SET type='changed' WHERE encounter_id=?", (encounter_id,))
    with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM audit_events WHERE encounter_id=?", (encounter_id,))

    assert len(store.list_audit(encounter_id)) == 1
