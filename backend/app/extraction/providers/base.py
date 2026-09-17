"""Provider boundary. A provider returns RAW TEXT and metadata only.
Parsing, validation, grounding, and flagging happen in app/extraction/pipeline.py
so provider output is held to the same contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.encounter import EncounterContext, Transcript


@dataclass(frozen=True)
class ProviderRequest:
    context: EncounterContext
    transcript: Transcript
    repair_hint: str | None = None  # set on the single retry: validation error summary from attempt 1


@dataclass(frozen=True)
class ProviderResponse:
    raw_text: str  # JSON text of the envelope (for tool use: json.dumps(tool_input))
    model: str | None


class ProviderError(Exception):
    """Transport/auth/timeout failure. Pipeline records PROVIDER_ERROR and fails the run."""


class ExtractionProvider(Protocol):
    name: Literal["mock"]
    supports_repair_retry: bool  # False for the deterministic fixture provider

    def extract(self, request: ProviderRequest) -> ProviderResponse: ...


# MockProvider returns fixtures/extraction/<fixture_id>.<scenario>.json verbatim.
# CARDIOFLOW_MOCK_SCENARIO lets tests force contract failures such as invalid_json.
