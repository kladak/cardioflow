from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from app.api.schemas import FixtureListItem

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "encounters"


def fixture_data(fixture_id: str) -> dict[str, Any]:
    path = ROOT / f"{fixture_id}.json"
    if not path.exists():
        raise KeyError(fixture_id)
    return cast(dict[str, Any], json.loads(path.read_text()))


def list_fixtures() -> list[FixtureListItem]:
    return [
        FixtureListItem(id=d["fixture_id"], title=d["title"], description=d["description"], purpose=d["purpose"])
        for d in (json.loads(p.read_text()) for p in sorted(ROOT.glob("*.json")))
    ]
