"""Optimization tools for the four-platform RAGOps corpus."""
from __future__ import annotations

from uuid import uuid4
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
CANDIDATE_INDEX_DIR = PROJECT_ROOT / "vector_store" / "candidates"
TARGET_PLATFORMS = ("absher", "balady", "najiz", "sakani")
EMBEDDING_MODEL = "text-embedding-3-small"
BASELINE_K = 4


def change_top_k(vector_store: FAISS, new_k: int = 6):
    """Return a retriever using a different Top-K without mutating the index."""
    if int(new_k) < 1:
        raise ValueError("new_k must be >= 1")
    return vector_store.as_retriever(
        search_kwargs={"k": int(new_k)}
    )


def rewrite_query(original_query: str) -> str:
    """Rewrite a natural Arabic query for retrieval across all four platforms."""
    original_query = str(original_query).strip()
    if not original_query:
        raise ValueError("original_query must not be empty")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "أنت خبير في تحسين الاستعلامات لنظام استرجاع وثائق "
                "الخدمات الحكومية السعودية. قاعدة المعرفة الحالية تشمل "
                "أبشر وناجز وبلدي وسكني. أعد صياغة سؤال المستخدم بصياغة "
                "واضحة ومختصرة وتحافظ على نفس المعنى، مع استخدام المصطلحات "
                "الرسمية المحتملة للخدمة لتحسين الاسترجاع. لا تجب عن السؤال "
                "ولا تضف معلومات جديدة؛ أعد الاستعلام فقط.",
            ),
            (
                "human",
                "السؤال الأصلي: {query}\n\n"
                "الاستعلام المحسن للبحث:",
            ),
        ]
    )

    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"query": original_query}).strip()


def _collect_final_files(
    platforms: Tuple[str, ...] = TARGET_PLATFORMS,
) -> List[Path]:
    files: List[Path] = []

    for platform in platforms:
        platform_dir = KNOWLEDGE_BASE_DIR / platform
        if not platform_dir.exists():
            continue

        for service_dir in sorted(
            p for p in platform_dir.iterdir() if p.is_dir()
        ):
            final_file = service_dir / "content_final.md"
            if final_file.exists():
                files.append(final_file)

    return files


def _build_splits(
    files: List[Path],
    chunk_size: int,
    chunk_overlap: int,
):
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    all_splits = []

    for file_path in files:
        relative = file_path.relative_to(KNOWLEDGE_BASE_DIR)
        platform = relative.parts[0]
        service = relative.parts[1]

        markdown_text = file_path.read_text(encoding="utf-8")
        header_splits = markdown_splitter.split_text(markdown_text)
        splits = text_splitter.split_documents(header_splits)

        source = file_path.relative_to(PROJECT_ROOT).as_posix()

        for chunk_index, split in enumerate(splits):
            split.metadata.update(
                {
                    "platform": platform,
                    "service": service,
                    "source": source,
                    "chunk_index": chunk_index,
                }
            )

        all_splits.extend(splits)

    return all_splits


def rechunk_and_reindex(
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> Dict[str, Any]:
    """Build a NON-DESTRUCTIVE candidate index from final validated files.

    The active index is never overwritten here. Validation must compare this
    candidate against the baseline before a later promotion step is allowed.
    """
    if chunk_size < 100:
        raise ValueError("chunk_size is too small")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be >= 0 and smaller than chunk_size"
        )

    files = _collect_final_files()
    if not files:
        raise FileNotFoundError(
            "No content_final.md files found in the four-platform corpus."
        )

    all_splits = _build_splits(
        files,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = FAISS.from_documents(all_splits, embeddings)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix = uuid4().hex[:8]
    relative_output_path = (
        Path("vector_store")
        / "candidates"
        / f"rechunk_{chunk_size}_{chunk_overlap}_{stamp}_{unique_suffix}"
    )
    output_path = PROJECT_ROOT / relative_output_path
    output_path.mkdir(parents=True, exist_ok=True)

    # FAISS on Windows can fail when its native writer receives an absolute
    # path containing non-ASCII characters (for example an Arabic Desktop
    # folder name). Save through an ASCII relative path while temporarily
    # using the project root as the working directory. pathlib still creates
    # the real destination directory above, and the active index is untouched.
    previous_cwd = Path.cwd()
    try:
        os.chdir(PROJECT_ROOT)
        vectorstore.save_local(str(relative_output_path))
    finally:
        os.chdir(previous_cwd)

    return {
        "status": "candidate_built",
        "vector_store": vectorstore,
        "candidate_index_path": relative_output_path.as_posix(),
        "platforms": list(TARGET_PLATFORMS),
        "final_files": len(files),
        "chunks": len(all_splits),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "embedding_model": EMBEDDING_MODEL,
    }
