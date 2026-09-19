"""Unified four-platform knowledge corpus for RAGOps.

Loads the 24 government service guides from Absher, Balady, Najiz, and
Sakani into the same chunk contract used by Jawaher's VectorStore and
MonitoringAgent. The active embedding backend remains configurable:
OpenAI + FAISS for the live path, with the project's existing fallbacks for
offline tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
ABSHEER_CHUNKS_PATH = KNOWLEDGE_BASE_DIR / "absher" / "chunks.jsonl"
PLATFORMS_WITH_MARKDOWN = ("balady", "najiz", "sakani")


def _fallback_split_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Small dependency-free fallback used only if LangChain is unavailable."""
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: List[str] = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        candidate = cleaned[start:end]
        if end < len(cleaned):
            boundary = max(candidate.rfind("\n\n"), candidate.rfind("\n"), candidate.rfind(" "))
            if boundary >= int(chunk_size * 0.55):
                end = start + boundary
                candidate = cleaned[start:end]
        candidate = candidate.strip()
        if candidate:
            chunks.append(candidate)
        if end >= len(cleaned):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks


def split_markdown(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """Split long service guides while preserving an offline fallback."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        return _fallback_split_text(text, chunk_size, chunk_overlap)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "،", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def load_absher_chunks(path: Path = ABSHEER_CHUNKS_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Absher chunks file not found: {path}")
    chunks: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        item.setdefault("platform", "Absher")
        item.setdefault("source_file", item.get("source_documents", [""])[0] if item.get("source_documents") else "")
        item.setdefault("chunk_index", 0)
        chunks.append(item)
    return chunks


def _service_name_from_text(text: str, service_id: str) -> str:
    for line in text.splitlines():
        value = line.strip().lstrip("#").strip()
        if value:
            return value
    return service_id.replace("_", " ")


def load_markdown_platform_chunks(
    platform: str,
    *,
    knowledge_base_dir: Path = KNOWLEDGE_BASE_DIR,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[Dict[str, Any]]:
    platform_dir = knowledge_base_dir / platform
    if not platform_dir.exists():
        raise FileNotFoundError(f"Platform folder not found: {platform_dir}")

    chunks: List[Dict[str, Any]] = []
    for service_dir in sorted(path for path in platform_dir.iterdir() if path.is_dir()):
        content_path = service_dir / "content_final.md"
        if not content_path.exists():
            continue
        text = content_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        service_id = service_dir.name
        service_name_ar = _service_name_from_text(text, service_id)
        relative_source = content_path.relative_to(PROJECT_ROOT).as_posix()
        for index, chunk_text in enumerate(split_markdown(text, chunk_size, chunk_overlap)):
            chunks.append(
                {
                    "chunk_id": f"{platform}__{service_id}__chunk__{index}",
                    "text": chunk_text,
                    "service_id": service_id,
                    "service_name_ar": service_name_ar,
                    "service_name_en": service_id.replace("_", " ").title(),
                    "category_ar": "خدمات حكومية رقمية",
                    "category_en": "Government Digital Services",
                    "chunk_type": "content",
                    "section_title_ar": service_name_ar,
                    "section_title_en": service_id.replace("_", " ").title(),
                    "source_documents": [relative_source],
                    "data_completeness": "full",
                    "platform": platform,
                    "source_file": relative_source,
                    "chunk_index": index,
                    "char_len": len(chunk_text),
                }
            )
    return chunks


def load_unified_chunks(
    *,
    project_root: Path = PROJECT_ROOT,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[Dict[str, Any]]:
    """Load all four platforms into one normalized chunk collection."""
    knowledge_base_dir = project_root / "knowledge_base"
    chunks = load_absher_chunks(knowledge_base_dir / "absher" / "chunks.jsonl")
    for platform in PLATFORMS_WITH_MARKDOWN:
        chunks.extend(
            load_markdown_platform_chunks(
                platform,
                knowledge_base_dir=knowledge_base_dir,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )
    if not chunks:
        raise ValueError("Unified corpus is empty")
    return chunks


def corpus_summary(chunks: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(chunks)
    platforms: Dict[str, set[str]] = {}
    for item in items:
        platforms.setdefault(str(item.get("platform")), set()).add(str(item.get("service_id")))
    return {
        "total_chunks": len(items),
        "platforms": {
            platform: {
                "service_count": len(services),
                "services": sorted(services),
            }
            for platform, services in sorted(platforms.items())
        },
        "total_services": len({item.get("service_id") for item in items}),
    }


def build_unified_store(
    backend: Optional[str] = None,
    *,
    project_root: Path = PROJECT_ROOT,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
):
    """Build the team's real VectorStore over all four platforms.

    `backend=None` uses the project's configured live default (OpenAI + FAISS)
    and existing fallback chain. Tests can pass `backend="tfidf"`.
    """
    try:
        from scripts.embeddings import get_embedder
        from scripts.retrieval import VectorStore
    except ModuleNotFoundError:
        from embeddings import get_embedder
        from retrieval import VectorStore

    chunks = load_unified_chunks(
        project_root=project_root,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    store = VectorStore(embedder=get_embedder(backend)).build(chunks)
    return store, corpus_summary(chunks)
