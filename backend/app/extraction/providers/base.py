"""Provider boundary. A provider returns RAW TEXT and metadata only.
Parsing, validation, grounding, and flagging happen in app/extraction/pipeline.py
(to be implemented) so every provider is held to the same contract."""

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
    name: Literal["mock", "anthropic"]
    supports_repair_retry: bool  # mock: False (deterministic); anthropic: True

    def extract(self, request: ProviderRequest) -> ProviderResponse: ...


# Implementations to build:
#   mock.py      — MockProvider(scenario_map): returns fixtures/extraction/<fixture_id>.<scenario>.json
#                  text verbatim; scenario defaults to "default"; unknown fixture ⇒ envelope with facts: [].
#                  Env CARDIOFLOW_MOCK_SCENARIO lets tests/E2E force e.g. "invalid_json".
#   anthropic.py — AnthropicProvider(model, api_key, timeout_s=60): Messages API with one tool
#                  `record_extraction` whose input_schema = extraction_json_schema(), tool_choice forced,
#                  temperature 0. raw_text = json.dumps(tool_use.input). SDK errors ⇒ ProviderError.
