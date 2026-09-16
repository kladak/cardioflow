from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARDIOFLOW_", extra="ignore")

    db_path: Path = Path("data/cardioflow.db")
    extraction_provider: Literal["mock", "anthropic"] = "mock"
    mock_scenario: str = "default"
    demo_clinician: str = "Dr. A. Reyes"
    cors_origins: str = "http://localhost:3000"
