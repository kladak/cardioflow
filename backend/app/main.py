# mypy: disable-error-code=no-untyped-def
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.schemas import (
    CreateEncounterRequest,
    CreateExportRequest,
    EncounterListItem,
    EncounterView,
    ExportDetail,
    FixtureListItem,
    NoteSectionRequest,
    PolicyView,
    ReviewFactRequest,
    RunExtractionRequest,
)
from app.core.clock import SystemClock
from app.core.ids import new_id
from app.core.settings import Settings
from app.domain.encounter import AuditEvent, NoteSectionKey
from app.extraction.providers.mock import MockProvider
from app.policy.engine import load_policy
from app.services.encounter_service import EncounterService, ServiceError
from app.services.fixtures import list_fixtures
from app.services.view_builder import build_view, list_item
from app.store.sqlite import NotFound, RevisionConflict, SQLiteStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="CardioFlow API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    store = SQLiteStore(settings.db_path)
    if settings.extraction_provider != "mock":
        raise RuntimeError("This demo slice supports the deterministic mock provider only")
    service = EncounterService(
        store, MockProvider(settings.mock_scenario), SystemClock(), new_id, settings.demo_clinician
    )

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse(
            status_code=404, content={"error": {"code": "not_found", "message": "Encounter not found.", "details": {}}}
        )

    @app.exception_handler(RevisionConflict)
    async def revision_conflict(_: Request, exc: RevisionConflict):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "revision_conflict",
                    "message": "This encounter changed elsewhere.",
                    "details": {"current_revision": exc.current_revision},
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request did not match the API contract.",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "provider": settings.extraction_provider}

    @app.get("/api/fixtures", response_model=list[FixtureListItem])
    def fixtures():
        return list_fixtures()

    @app.get("/api/policies/{policy_id}", response_model=PolicyView)
    def policy(policy_id: str):
        p = load_policy()
        if p.id != policy_id:
            raise ServiceError("not_found", "Policy not found.", 404)
        return {"policy": p}

    @app.post("/api/encounters", status_code=201, response_model=EncounterView)
    def create(req: CreateEncounterRequest):
        return service.create(req)

    @app.get("/api/encounters", response_model=list[EncounterListItem])
    def encounters():
        return [list_item(e) for e in store.list_encounters()]

    @app.get("/api/encounters/{encounter_id}", response_model=EncounterView)
    def encounter(encounter_id: str):
        return build_view(store.load(encounter_id), settings.extraction_provider)

    @app.post("/api/encounters/{encounter_id}/extraction-runs", response_model=EncounterView)
    def extract(encounter_id: str, req: RunExtractionRequest):
        return service.extract(encounter_id, req.expected_revision)

    @app.post("/api/encounters/{encounter_id}/facts/{fact_id}/review", response_model=EncounterView)
    def review(encounter_id: str, fact_id: str, req: ReviewFactRequest):
        return service.review(encounter_id, fact_id, req)

    @app.post("/api/encounters/{encounter_id}/note-sections/{key}", response_model=EncounterView)
    def note(encounter_id: str, key: NoteSectionKey, req: NoteSectionRequest):
        return service.note_action(encounter_id, key, req)

    @app.post("/api/encounters/{encounter_id}/exports", status_code=201, response_model=ExportDetail)
    def export(encounter_id: str, req: CreateExportRequest):
        e = service.create_export(encounter_id, req.expected_revision)
        return ExportDetail(
            id=e.id,
            generated_at=e.generated_at,
            generated_by=e.generated_by,
            review_revision=e.review_revision,
            is_stale=False,
            bundle=e.bundle,
            manifest=e.manifest,
            excluded=e.excluded,
        )

    @app.get("/api/encounters/{encounter_id}/exports/{export_id}", response_model=ExportDetail)
    def get_export(encounter_id: str, export_id: str):
        enc = store.load(encounter_id)
        e = next((x for x in enc.exports if x.id == export_id), None)
        if not e:
            raise ServiceError("not_found", "Export not found.", 404)
        return ExportDetail(
            id=e.id,
            generated_at=e.generated_at,
            generated_by=e.generated_by,
            review_revision=e.review_revision,
            is_stale=e.review_revision != enc.review_revision,
            bundle=e.bundle,
            manifest=e.manifest,
            excluded=e.excluded,
        )

    @app.get("/api/encounters/{encounter_id}/audit", response_model=list[AuditEvent])
    def audit(encounter_id: str):
        return store.list_audit(encounter_id)

    return app


app = create_app()
