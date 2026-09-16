import re
from datetime import date, datetime


def resolve_spoken_date(text: str | None, encounter_date: date) -> date | None:
    if not text:
        return None
    clean = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip(), flags=re.I)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            pass
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(clean, fmt).date().replace(year=encounter_date.year)
            return parsed if parsed <= encounter_date else parsed.replace(year=encounter_date.year - 1)
        except ValueError:
            pass
    return None
