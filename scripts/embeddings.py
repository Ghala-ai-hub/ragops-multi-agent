"""
embeddings.py
-------------
Pluggable embedding backends for retrieval.py.

As of this revision, Sentence Transformers is the DEFAULT / PRIMARY backend
(semantic embeddings generalize far better across MSA/Saudi-colloquial
Arabic than lexical TF-IDF overlap — see the two colloquial queries flagged
in README section 3/5). TF-IDF is retained as the offline BASELINE and as an
automatic FALLBACK: if `sentence-transformers` (the package) or its model
weights can't be loaded — no package installed, no outbound network access,
etc. — `get_embedder()` catches that, logs exactly why, and hands back a
working `TfidfEmbedder` instead of crashing the pipeline. The returned
embedder always carries `.fallback_from` / `.fallback_reason` (both `None`
on a clean load) so callers can tell a real semantic run apart from a
TF-IDF fallback that only *looks* like one — see `VectorStore.backend_info()`
in retrieval.py, which is what evaluation.py and the README rely on to
report honestly.

Two backends, one interface (`fit`, `transform_query`, `transform_corpus`):

- SentenceTransformerEmbedder (default/primary): wraps `sentence-transformers`,
  model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  (multilingual, includes Arabic). Requires the package plus, on first use,
  network access to download the model weights.

- TfidfEmbedder (baseline + fallback): scikit-learn TF-IDF + word n-grams.
  Works fully offline, deterministic, and is what this sandbox actually
  exercises end to end, because it has no outbound network access — see
  README "What was actually run" for the exact, current boundary between
  tested and provided-but-untested code.

get_embedder(name) is the single switch: change ABSHER_EMBEDDER in
config.example.env (or the env var directly) to move between them without
touching retrieval.py.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional, Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from text_utils import normalize_arabic

# Default backend as of this revision. Was "tfidf"; now "sentence-transformers"
# per the decision to make semantic retrieval primary for Arabic/dialect
# robustness. Change here (or via ABSHER_EMBEDDER) to move the whole
# pipeline's default without touching retrieval.py/evaluation.py.
DEFAULT_EMBEDDER_BACKEND = "sentence-transformers"
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    def fit(self, corpus: List[str]) -> None: ...
    def transform_corpus(self, corpus: List[str]) -> np.ndarray: ...
    def transform_query(self, query: str) -> np.ndarray: ...


class TfidfEmbedder:
    """Offline-friendly default. Word (1,2)-gram TF-IDF over the corpus,
    which is small (a few dozen chunks) so a sparse vector space model is a
    perfectly adequate, fully-testable substitute for a neural embedder at
    this scale — and it is honest about being one."""

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
    """DEFAULT / PRIMARY backend. Multilingual semantic embedder — requires
    the `sentence-transformers` package and, on first use, network access
    to download the model weights. Neither is available in this sandbox
    (confirmed: `pip install sentence-transformers` fails with no matching
    distribution, and direct HTTPS requests to pypi.org / huggingface.co
    both return 403 Forbidden), so this class is provided ready-to-run for
    the team on a machine that has internet access; it is NOT covered by
    `tests/` here — see README "What was actually run"."""

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


def get_embedder(name: str | None = None) -> Embedder:
    """Resolve the requested backend (explicit `name` > ABSHER_EMBEDDER env
    var > DEFAULT_EMBEDDER_BACKEND, currently "sentence-transformers").

    If sentence-transformers is requested but cannot actually be loaded
    (package missing, or model-weight download fails for lack of network),
    this does NOT raise and does NOT silently pretend to be semantic — it
    prints one clear warning to stderr naming the real reason, and returns a
    `TfidfEmbedder` with `.fallback_from="sentence-transformers"` and
    `.fallback_reason=<the actual exception>` set, so every caller
    (VectorStore.backend_info(), evaluation.py, monitoring logs) can report
    truthfully which backend actually produced a given result.
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
    raise ValueError(f"Unknown embedder backend: {requested!r}")
