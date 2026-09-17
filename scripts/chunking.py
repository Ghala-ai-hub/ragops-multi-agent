"""
chunking.py
-----------
Person 1 (Absher RAG improvement) — Step 2: chunking strategy.

Why this strategy (addresses MVP problem "Chunking Quality")
==============================================================
We do NOT split documents into fixed-size token windows. Absher guides are
short, highly structured documents (definition -> conditions -> numbered UI
steps -> fees -> FAQ), and a fixed-size splitter would either:
  (a) merge unrelated sections into one chunk (e.g. login steps + payment
      steps + fees all in one window), hurting precision, or
  (b) cut a single idea (e.g. one FAQ answer, one eligibility condition)
      across two chunks, hurting recall and readability.

Instead we chunk along the document's own semantic boundaries, one chunk per:
  - service overview  (definition + eligibility conditions)
  - each step "phase"  (access / eligibility+payment / confirmation /
    delivery / payment — as pre-grouped in data_processing.py, NOT one chunk
    per tiny UI click)
  - fees + delivery notes (only if the service actually states any)
  - important notes (only if present)
  - each FAQ question+answer pair (already a natural, self-contained unit)

Every chunk is prefixed with the Arabic service name so it stays
understandable if retrieved on its own, out of order, with no neighbouring
chunks — this is the "preserve enough context" requirement.

Every chunk carries metadata: chunk_id, service_id, service name (ar/en),
category, source document(s), section title, chunk_type, and
data_completeness (flags the exit/reentry visa service, which is FAQ-only).

Additionally (for the Monitoring -> Diagnosis Agent contract, see
monitoring_agent.py): each chunk also carries a single `source_file` (the
specific file its content was drawn from — resolved deterministically from
chunk_type + the service's known source files, not guessed), a 0-based
`chunk_index` (its position among chunks from that same source_file), and a
constant `platform` ("Absher") since Diagnosis Agent is shared across all of
the team's platforms (Absher/Najiz/Balady/Sakani) and needs to know which
one a given result came from. `source_documents` (the full list) is kept
too, unchanged, for broader provenance/audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# Fallback platform tag, only used if a service dict genuinely has no
# "platform" key of its own (e.g. hand-built test fixtures). Every real
# ServiceRecord now carries its own `platform` field (added in
# data_processing.py) and chunk_service() reads that first — this constant
# is no longer the sole source of truth, just a safety-net default so this
# module still works with older/minimal service dicts. Sakani/Najiz/Balady
# chunks get their platform from their own service data, not from here.
PLATFORM = "Absher"


@dataclass
class Chunk:
    chunk_id: str
    text: str
    service_id: str
    service_name_ar: str
    service_name_en: str
    category_ar: str
    category_en: str
    chunk_type: str          # overview | step | fees_delivery | notes | faq
    section_title_ar: str
    section_title_en: str
    source_documents: List[str]
    data_completeness: str   # full | faq_only
    platform: str = PLATFORM
    source_file: str = ""    # the ONE file this chunk's text actually came from
    chunk_index: int = 0     # 0-based position among chunks from that source_file
    char_len: int = 0

    def finalize(self) -> "Chunk":
        self.char_len = len(self.text)
        return self


def _header(service_name_ar: str) -> str:
    return f"[خدمة: {service_name_ar}] "


def _pick_source_file(chunk_type: str, source_files: List[str]) -> str:
    """Deterministically resolve which single file a chunk's content came
    from, given the service's known source files. FAQ items come from the
    file with "faq" in its name; everything else (overview/step/fees/notes)
    comes from the "guide" file. If a service has no guide file (the
    FAQ-only exit/reentry-visa service), every chunk_type correctly falls
    back to the single FAQ file that's actually there — reflecting reality,
    not guessing."""
    needle = "faq" if chunk_type == "faq" else "guide"
    for f in source_files:
        if needle in f:
            return f
    return source_files[0]


def chunk_service(svc: Dict[str, Any]) -> List[Chunk]:
    chunks: List[Chunk] = []
    sid = svc["service_id"]
    name_ar = svc["service_name_ar"]
    name_en = svc["service_name_en"]
    cat_ar = svc["category_ar"]
    cat_en = svc["category_en"]
    completeness = svc["data_completeness"]
    sources = svc["source_files"]
    platform = svc.get("platform", PLATFORM)
    header = _header(name_ar)

    # 1) overview chunk = definition + conditions
    overview_parts = [svc["definition_ar"]]
    if svc["conditions_ar"]:
        conditions_text = "\n".join(f"- {c}" for c in svc["conditions_ar"])
        overview_parts.append(f"شروط الأهلية:\n{conditions_text}")
    overview_text = header + "\n\n".join(overview_parts)
    chunks.append(Chunk(
        chunk_id=f"{sid}__overview",
        text=overview_text,
        service_id=sid, service_name_ar=name_ar, service_name_en=name_en,
        category_ar=cat_ar, category_en=cat_en,
        platform=platform,
        chunk_type="overview",
        section_title_ar="نبذة عن الخدمة وشروط الأهلية",
        section_title_en="Service overview & eligibility conditions",
        source_documents=sources, data_completeness=completeness,
        source_file=_pick_source_file("overview", sources),
    ).finalize())

    # 2) one chunk per step phase
    for step in svc["steps"]:
        text = f"{header}({step['title_ar']}): {step['text_ar']}"
        chunks.append(Chunk(
            chunk_id=f"{sid}__step__{step['phase_id']}",
            text=text,
            service_id=sid, service_name_ar=name_ar, service_name_en=name_en,
            category_ar=cat_ar, category_en=cat_en,
            platform=platform,
            chunk_type="step",
            section_title_ar=step["title_ar"], section_title_en=step["title_en"],
            source_documents=sources, data_completeness=completeness,
            source_file=_pick_source_file("step", sources),
        ).finalize())

    # 3) fees + delivery notes (skip if genuinely empty/"not stated")
    fees = svc.get("fees_notes_ar", "")
    delivery = svc.get("delivery_notes_ar", "")
    if fees or delivery:
        parts = []
        if fees:
            parts.append(f"الرسوم: {fees}")
        if delivery:
            parts.append(f"التوصيل: {delivery}")
        chunks.append(Chunk(
            chunk_id=f"{sid}__fees_delivery",
            text=header + "\n".join(parts),
            service_id=sid, service_name_ar=name_ar, service_name_en=name_en,
            category_ar=cat_ar, category_en=cat_en,
            platform=platform,
            chunk_type="fees_delivery",
            section_title_ar="الرسوم والتوصيل", section_title_en="Fees & delivery",
            source_documents=sources, data_completeness=completeness,
            source_file=_pick_source_file("fees_delivery", sources),
        ).finalize())

    # 4) important notes
    if svc["important_notes_ar"]:
        notes_text = "\n".join(f"- {n}" for n in svc["important_notes_ar"])
        chunks.append(Chunk(
            chunk_id=f"{sid}__notes",
            text=header + notes_text,
            service_id=sid, service_name_ar=name_ar, service_name_en=name_en,
            category_ar=cat_ar, category_en=cat_en,
            platform=platform,
            chunk_type="notes",
            section_title_ar="ملاحظات هامة", section_title_en="Important notes",
            source_documents=sources, data_completeness=completeness,
            source_file=_pick_source_file("notes", sources),
        ).finalize())

    # 5) one chunk per FAQ item (already a natural semantic unit)
    for i, item in enumerate(svc["faq"]):
        text = f"{header}س: {item['question_ar']}\nج: {item['answer_ar']}"
        chunks.append(Chunk(
            chunk_id=f"{sid}__faq__{i}",
            text=text,
            service_id=sid, service_name_ar=name_ar, service_name_en=name_en,
            category_ar=cat_ar, category_en=cat_en,
            platform=platform,
            chunk_type="faq",
            section_title_ar="سؤال شائع", section_title_en="FAQ item",
            source_documents=sources, data_completeness=completeness,
            source_file=_pick_source_file("faq", sources),
        ).finalize())

    # 6) chunk_index: 0-based position among chunks sharing the same
    # resolved source_file, in creation order (overview/steps/fees/notes
    # before faq items, matching each file's natural reading order).
    counters: Dict[str, int] = {}
    for c in chunks:
        c.chunk_index = counters.get(c.source_file, 0)
        counters[c.source_file] = c.chunk_index + 1

    return chunks


def build_chunks(documents_path: Path = PROCESSED_DIR / "documents.json") -> List[Chunk]:
    payload = json.loads(documents_path.read_text(encoding="utf-8"))
    all_chunks: List[Chunk] = []
    for svc in payload["services"]:
        all_chunks.extend(chunk_service(svc))
    return all_chunks


def save_chunks(out_path: Path = PROCESSED_DIR / "chunks.jsonl") -> Path:
    chunks = build_chunks()
    with out_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    return out_path


if __name__ == "__main__":
    path = save_chunks()
    chunks = build_chunks()
    lengths = [c.char_len for c in chunks]
    print(f"Wrote {len(chunks)} chunks to {path}")
    print(f"Chunk length (chars): min={min(lengths)} max={max(lengths)} "
          f"avg={sum(lengths)/len(lengths):.0f}")
    by_type: Dict[str, int] = {}
    for c in chunks:
        by_type[c.chunk_type] = by_type.get(c.chunk_type, 0) + 1
    print("By type:", by_type)
