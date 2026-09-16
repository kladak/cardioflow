from __future__ import annotations

from app.domain.encounter import ExtractionIssue, ExtractionIssueKind, Transcript
from app.domain.facts import EvidenceSpan
from app.extraction.contract import EvidenceRef


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    out: list[str] = []
    idx: list[int] = []
    last_space = True
    for i, raw in enumerate(text):
        ch = {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"}.get(raw, raw).casefold()
        if ch.isspace():
            if not last_space:
                out.append(" ")
                idx.append(i)
            last_space = True
        else:
            out.append(ch)
            idx.append(i)
            last_space = False
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def ground(
    ref: EvidenceRef, transcript: Transcript, item_index: int, fact_type: str
) -> tuple[EvidenceSpan | None, ExtractionIssue | None]:
    segment = transcript.segment(ref.segment_id)
    if not segment:
        return None, ExtractionIssue(
            kind=ExtractionIssueKind.UNKNOWN_SEGMENT,
            item_index=item_index,
            fact_type=fact_type,
            message=f"Unknown transcript segment {ref.segment_id}",
            detail={"quote": ref.quote},
        )
    start = segment.text.find(ref.quote)
    end = start + len(ref.quote)
    if start < 0:
        nt, mapping = _normalize_with_map(segment.text)
        nq, _ = _normalize_with_map(ref.quote)
        ns = nt.find(nq)
        if ns >= 0:
            start = mapping[ns]
            end = mapping[ns + len(nq) - 1] + 1
    if start < 0:
        return None, ExtractionIssue(
            kind=ExtractionIssueKind.QUOTE_NOT_FOUND,
            item_index=item_index,
            fact_type=fact_type,
            message=f"Quoted text was not found in {ref.segment_id}",
            detail={"quote": ref.quote},
        )
    quote = segment.text[start:end]
    return EvidenceSpan(
        segment_id=segment.id, char_start=start, char_end=end, quote=quote, speaker=segment.speaker
    ), None
