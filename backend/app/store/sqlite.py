from __future__ import annotations

import sqlite3
from pathlib import Path

from app.domain.encounter import AuditEvent, Encounter


class NotFound(Exception):
    pass


class RevisionConflict(Exception):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision


class SQLiteStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS encounters (
              id TEXT PRIMARY KEY, revision INTEGER NOT NULL, doc TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_events (
              id TEXT PRIMARY KEY, encounter_id TEXT NOT NULL, seq INTEGER NOT NULL,
              at TEXT NOT NULL, type TEXT NOT NULL, doc TEXT NOT NULL,
              UNIQUE(encounter_id, seq));
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
              SELECT RAISE(ABORT, 'audit_events are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN
              SELECT RAISE(ABORT, 'audit_events are append-only');
            END;
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def create(self, encounter: Encounter, events: list[AuditEvent]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO encounters VALUES (?,?,?,?,?)",
                (
                    encounter.id,
                    encounter.revision,
                    encounter.model_dump_json(),
                    encounter.created_at.isoformat(),
                    encounter.updated_at.isoformat(),
                ),
            )
            self._insert_events(db, events)

    def load(self, encounter_id: str) -> Encounter:
        with self._connect() as db:
            row = db.execute("SELECT doc FROM encounters WHERE id=?", (encounter_id,)).fetchone()
        if not row:
            raise NotFound(encounter_id)
        return Encounter.model_validate_json(row["doc"])

    def list_encounters(self) -> list[Encounter]:
        with self._connect() as db:
            rows = db.execute("SELECT doc FROM encounters ORDER BY updated_at DESC").fetchall()
        return [Encounter.model_validate_json(r["doc"]) for r in rows]

    def save(self, encounter: Encounter, events: list[AuditEvent], expected_revision: int) -> None:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM encounters WHERE id=?", (encounter.id,)).fetchone()
            if not row:
                raise NotFound(encounter.id)
            if row["revision"] != expected_revision:
                raise RevisionConflict(row["revision"])
            updated = db.execute(
                "UPDATE encounters SET revision=?, doc=?, updated_at=? WHERE id=? AND revision=?",
                (
                    encounter.revision,
                    encounter.model_dump_json(),
                    encounter.updated_at.isoformat(),
                    encounter.id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise RevisionConflict(row["revision"])
            self._insert_events(db, events)

    def _insert_events(self, db: sqlite3.Connection, events: list[AuditEvent]) -> None:
        for e in events:
            db.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?)",
                (e.id, e.encounter_id, e.seq, e.at.isoformat(), e.type, e.model_dump_json()),
            )

    def list_audit(self, encounter_id: str) -> list[AuditEvent]:
        self.load(encounter_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT doc FROM audit_events WHERE encounter_id=? ORDER BY seq", (encounter_id,)
            ).fetchall()
        return [AuditEvent.model_validate_json(r["doc"]) for r in rows]
