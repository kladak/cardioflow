from pathlib import Path

from app.extraction.providers.base import ProviderRequest, ProviderResponse


class MockProvider:
    name = "mock"
    supports_repair_retry = False

    def __init__(self, scenario: str = "default"):
        self.scenario = scenario
        self.root = Path(__file__).resolve().parents[3] / "fixtures" / "extraction"

    def extract(self, request: ProviderRequest) -> ProviderResponse:
        fixture = request.context.fixture_id
        if not fixture:
            return ProviderResponse('{"schema_version":"cardioflow.extraction.v1","facts":[]}', "fixture-v1")
        json_path = self.root / f"{fixture}.{self.scenario}.json"
        txt_path = self.root / f"{fixture}.{self.scenario}.txt"
        path = json_path if json_path.exists() else txt_path
        return ProviderResponse(path.read_text(), f"fixture-{self.scenario}")
