"""
embeddings.py
-------------
Pluggable embedding backends for retrieval.py.

As of this revision, OpenAI embeddings (via LangChain) are the DEFAULT /
PRIMARY backend, matching the project proposal's stated technology stack
(Python • LangChain • FAISS • OpenAI API). Sentence Transformers remains the
offline-friendly secondary option, and TF-IDF the fully-offline baseline and
final fallback. `get_embedder()` tries them in that order and falls back
automatically at each step — see the fallback chain below.

Three backends, all satisfying the same interface (`fit`, `transform_query`,
`transform_corpus`, `.name`):

- OpenAIEmbedder (default/primary): wraps `langchain_openai.OpenAIEmbeddings`.
  Requires `OPENAI_API_KEY` (read from a `.env` file via python-dotenv, or a
  real environment variable) and live network access to OpenAI's API for
  every embedding call — there is no local fallback once this backend is
  actually selected; if the key/network isn't available, get_embedder()
  falls back one tier instead of trying to run this at all.

- SentenceTransformerEmbedder (secondary): wraps `sentence-transformers`,
  model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  (multilingual, includes Arabic). Requires the package plus, on first use,
  network access to download the model weights.

- TfidfEmbedder (baseline + final fallback): scikit-learn TF-IDF + word
  n-grams. Works fully offline, deterministic, and is what this sandbox
  actually exercises end to end, because it has no outbound network access
  — see README "What was actually run" for the exact, current boundary
  between tested and provided-but-untested code.

get_embedder(name) is the single switch: change ABSHER_EMBEDDER in
config.example.env (or the env var directly) to move between them without
touching retrieval.py.

IMPORTANT CAVEAT (not fixed here, deliberately — see monitoring_agent.py):
`MonitoringAgent`'s QUERY_MISMATCH_THRESHOLD (0.12) was empirically
calibrated against TF-IDF's cosine-similarity score distribution. OpenAI's
and sentence-transformers' dense embeddings produce similarity scores on a
different numeric scale (dense embeddings tend to score meaningfully higher
even for loosely-related text), so a single shared threshold across all
three backends is a known, inherited limitation — not something introduced
by adding this backend. It was already true between TF-IDF and
sentence-transformers before this change. Recalibrating it needs real
empirical scores from an actual OpenAI-backed run, which this sandbox
cannot produce (no network access) — flagging clearly rather than guessing
a new number.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional, Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from text_utils import normalize_arabic

try:
    from dotenv import load_dotenv  # matches the team's other scripts
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — OPENAI_API_KEY must be a real env var instead

# Default backend as of this revision. Was "sentence-transformers"; now
# "openai" per the project proposal's stated technology stack (Python •
# LangChain • FAISS • OpenAI API). Change here (or via ABSHER_EMBEDDER) to
# move the whole pipeline's default without touching retrieval.py/evaluation.py.
DEFAULT_EMBEDDER_BACKEND = "openai"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"  # matches scripts/build_vectorstore.py
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    def fit(self, corpus: List[str]) -> None: ...
    def transform_corpus(self, corpus: List[str]) -> np.ndarray: ...
    def transform_query(self, query: str) -> np.ndarray: ...


class TfidfEmbedder:
    """Offline-friendly final fallback. Word (1,2)-gram TF-IDF over the
    corpus, which is small (a few dozen chunks) so a sparse vector space
    model is a perfectly adequate, fully-testable substitute for a neural
    embedder at this scale — and it is honest about being one."""

    name = "tfidf"
    # Set by get_embedder() when this instance is standing in for a
    # different backend that failed to load; None on a plain, requested
    # TF-IDF run (e.g. the explicit baseline).
    fallback_from: Optional[str] = None
    fallback_reason: Optional[str] = None

    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            preprocessor=normalize_arabic,
        )
        self._fitted = False

    def fit(self, corpus: List[str]) -> None:
        self.vectorizer.fit(corpus)
        self._fitted = True

    def transform_corpus(self, corpus: List[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Call fit() before transform_corpus().")
        return self.vectorizer.transform(corpus)

    def transform_query(self, query: str) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Call fit() before transform_query().")
        return self.vectorizer.transform([query])


class SentenceTransformerEmbedder:
    """SECONDARY backend (offline-friendly semantic option). Multilingual
    semantic embedder — requires the `sentence-transformers` package and,
    on first use, network access to download the model weights. Neither is
    available in this sandbox (confirmed: `pip install sentence-transformers`
    fails with no matching distribution, and direct HTTPS requests to
    pypi.org / huggingface.co both return 403 Forbidden), so this class is
    provided ready-to-run for the team on a machine that has internet
    access; it is NOT covered by `tests/` here — see README "What was
    actually run"."""

    name = "sentence-transformers"
    fallback_from: Optional[str] = None
    fallback_reason: Optional[str] = None

    def __init__(self, model_name: str = DEFAULT_SENTENCE_TRANSFORMER_MODEL):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. Run "
                "`pip install sentence-transformers --break-system-packages` "
                "(requires internet access) or set ABSHER_EMBEDDER=tfidf."
            ) from e
        # Loading the model itself needs network access on first use (to
        # download weights) even when the package IS installed; this raises
        # its own (non-ImportError) exception on failure, which get_embedder()
        # catches broadly so both failure modes fall back the same way.
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

    def fit(self, corpus: List[str]) -> None:
        # No fitting step needed for a pretrained sentence encoder.
        return

    def transform_corpus(self, corpus: List[str]) -> np.ndarray:
        return np.asarray(self.model.encode(corpus, normalize_embeddings=True))

    def transform_query(self, query: str) -> np.ndarray:
        return np.asarray(self.model.encode([query], normalize_embeddings=True))


class OpenAIEmbedder:
    """DEFAULT / PRIMARY backend — matches the project proposal's stated
    technology stack (Python • LangChain • FAISS • OpenAI API) exactly.
    Requires `OPENAI_API_KEY` (via `.env` or a real environment variable)
    and live network access to OpenAI's API for every embedding call.
    `retrieval.py`'s VectorStore uses `self.langchain_embeddings` directly
    to build a real `langchain_community.vectorstores.FAISS` index — the
    `fit`/`transform_corpus`/`transform_query` methods below exist only so
    this class still satisfies the same Embedder protocol as the other two
    backends for any code that type-checks or calls them directly.

    NOT exercised end to end in this sandbox: no outbound network access
    here to actually call the OpenAI API (same limitation documented for
    SentenceTransformerEmbedder above) — provided ready-to-run for the team
    on a machine with a real OPENAI_API_KEY and network access."""

    name = "openai"
    fallback_from: Optional[str] = None
    fallback_reason: Optional[str] = None

    def __init__(self, model_name: str = DEFAULT_OPENAI_EMBEDDING_MODEL):
        try:
            from langchain_openai import OpenAIEmbeddings  # type: ignore
        except ImportError as e:
            raise ImportError(
                "langchain-openai is not installed. Run "
                "`pip install langchain-openai langchain-community faiss-cpu` "
                "or set ABSHER_EMBEDDER=sentence-transformers / tfidf."
            ) from e
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to a .env file at the "
                "project root (see config.example.env) or set it as a real "
                "environment variable."
            )
        self.model_name = model_name
        self.langchain_embeddings = OpenAIEmbeddings(model=model_name, api_key=api_key)

    def fit(self, corpus: List[str]) -> None:
        # Stateless API-backed embedder — no local fitting step. (VectorStore
        # does not actually call this for the "openai" backend; it builds a
        # FAISS index directly instead — see retrieval.py.)
        return

    def transform_corpus(self, corpus: List[str]) -> np.ndarray:
        return np.asarray(self.langchain_embeddings.embed_documents(corpus))

    def transform_query(self, query: str) -> np.ndarray:
        return np.asarray([self.langchain_embeddings.embed_query(query)])


def get_embedder(name: str | None = None) -> Embedder:
    """Resolve the requested backend (explicit `name` > ABSHER_EMBEDDER env
    var > DEFAULT_EMBEDDER_BACKEND, currently "openai").

    Fallback chain: openai -> sentence-transformers -> tfidf. If a backend
    can't actually be loaded (missing package, missing API key, no network),
    this does NOT raise and does NOT silently pretend to be a different
    backend — it prints one clear warning to stderr naming the real reason,
    tries the next tier down, and the returned embedder always carries
    `.fallback_from` / `.fallback_reason` (both `None` on a clean load) so
    every caller (VectorStore.backend_info(), evaluation.py, monitoring
    logs) can report truthfully which backend actually produced a given
    result.
    """
    requested = (name or os.environ.get("ABSHER_EMBEDDER", DEFAULT_EMBEDDER_BACKEND)).lower()

    if requested == "tfidf":
        return TfidfEmbedder()

    if requested in ("sentence-transformers", "sentence_transformers", "st"):
        model_name = os.environ.get("SENTENCE_TRANSFORMERS_MODEL", DEFAULT_SENTENCE_TRANSFORMER_MODEL)
        try:
            return SentenceTransformerEmbedder(model_name=model_name)
        except Exception as e:  # noqa: BLE001 - any load failure -> fallback, not a crash
            fallback = TfidfEmbedder()
            fallback.fallback_from = "sentence-transformers"
            fallback.fallback_reason = f"{type(e).__name__}: {e}"
            print(
                f"[embeddings] WARNING: requested backend 'sentence-transformers' "
                f"could not be loaded ({fallback.fallback_reason}); falling back to "
                f"'tfidf' so the pipeline keeps running. See README 'What was "
                f"actually run' for details.",
                file=sys.stderr,
            )
            return fallback

    if requested in ("openai", "faiss"):
        model_name = os.environ.get("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL)
        try:
            return OpenAIEmbedder(model_name=model_name)
        except Exception as e:  # noqa: BLE001 - any load failure -> fallback, not a crash
            openai_reason = f"{type(e).__name__}: {e}"
            print(
                f"[embeddings] WARNING: requested backend 'openai' could not "
                f"be loaded ({openai_reason}); falling back to "
                f"'sentence-transformers'.",
                file=sys.stderr,
            )
            fallback = get_embedder("sentence-transformers")
            if fallback.fallback_from:
                # sentence-transformers ALSO failed and already cascaded to
                # tfidf — chain both reasons instead of overwriting.
                fallback.fallback_reason = (
                    f"openai: {openai_reason} | sentence-transformers: {fallback.fallback_reason}"
                )
                fallback.fallback_from = "openai -> sentence-transformers"
            else:
                fallback.fallback_from = "openai"
                fallback.fallback_reason = openai_reason
            return fallback

    raise ValueError(f"Unknown embedder backend: {requested!r}")

