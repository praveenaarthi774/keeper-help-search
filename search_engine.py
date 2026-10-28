"""
search_engine.py  (lightweight / Render version)
=================================================

Same semantic search engine as the main app, but it uses **fastembed**
instead of sentence-transformers. fastembed runs a small ONNX embedding
model and does NOT pull in PyTorch, so memory use drops from ~1 GB to a few
hundred MB - small enough to run on a free 512 MB host like Render.

The model used, BAAI/bge-small-en-v1.5, produces 384-dimensional embeddings
(same size as all-MiniLM-L6-v2) and gives very similar semantic quality.

Pipeline (unchanged in spirit):
1. Each document -> a 384-d embedding vector (via fastembed / ONNX).
2. Vectors stored in a FAISS index (inner product == cosine, since we
   normalize to unit length).
3. Query -> embedding -> FAISS similarity search.
4. Hybrid re-rank: semantic score + a small boost when query words match a
   document title. Then threshold + top-k.
"""

from __future__ import annotations

import re
from typing import List, Dict

import numpy as np

# Model that fastembed will download once and cache. 384-dim, small, good.
MODEL_NAME = "BAAI/bge-small-en-v1.5"


# ---------------------------------------------------------------------------
# Light text helpers (used by keyword baseline + title-boost).
# ---------------------------------------------------------------------------
_WS_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]")


def clean_text(text: str) -> str:
    text = text.lower()
    text = _WS_RE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    text = _NON_WORD_RE.sub(" ", text.lower())
    return [t for t in text.split() if t]


def _normalize_rows(mat: np.ndarray) -> np.ndarray:
    """Scale each row vector to unit length (so inner product == cosine)."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class SemanticSearchEngine:
    """Embeds documents with fastembed and searches them by meaning via FAISS."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self.model = None
        self.index = None
        self.documents: List[Dict] = []

    # -- model loading -----------------------------------------------------
    def _load_model(self) -> None:
        if self.model is None:
            from fastembed import TextEmbedding

            print(f"Loading fastembed model '{self.model_name}' ...")
            self.model = TextEmbedding(model_name=self.model_name)
            print("Model loaded.")

    def _embed(self, texts: List[str]) -> np.ndarray:
        """Return a normalized float32 embedding matrix for the given texts."""
        self._load_model()
        # fastembed returns a generator of 1-D numpy arrays.
        vectors = list(self.model.embed(texts))
        mat = np.array(vectors, dtype="float32")
        return _normalize_rows(mat)

    # -- index building ----------------------------------------------------
    def build_index(self, documents: List[Dict]) -> None:
        if not documents:
            raise ValueError("Cannot build an index with no documents.")

        import faiss

        self.documents = documents
        texts = [f"{d['title']}. {d['content']}" for d in documents]
        embeddings = self._embed(texts)

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings)

    # -- semantic search ---------------------------------------------------
    def search(self, query: str, top_k: int = 5, min_score: float = 0.3) -> List[Dict]:
        if self.index is None:
            raise RuntimeError("Index not built. Call build_index() first.")

        query = (query or "").strip()
        if not query:
            raise ValueError("Query is empty.")

        query_vec = self._embed([query])

        n = len(self.documents)
        scores, indices = self.index.search(query_vec, n)

        q_words = set(tokenize(query))
        ranked = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            doc = self.documents[idx]
            semantic = float(score)
            title_words = set(tokenize(doc["title"]))
            overlap = (len(q_words & title_words) / len(q_words)) if q_words and title_words else 0.0
            combined = semantic + 0.25 * overlap
            ranked.append((combined, semantic, doc))

        ranked.sort(key=lambda t: t[0], reverse=True)

        results: List[Dict] = []
        for combined, semantic, doc in ranked:
            if semantic < min_score:
                continue
            results.append(
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "content": doc["content"],
                    "score": round(semantic, 4),
                }
            )
            if len(results) >= top_k:
                break
        return results

    # -- keyword baseline (for comparison) ---------------------------------
    def keyword_search(self, query: str, top_k: int = 5) -> List[Dict]:
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []
        scored = []
        for doc in self.documents:
            doc_tokens = set(tokenize(f"{doc['title']} {doc['content']}"))
            overlap = query_tokens & doc_tokens
            if not overlap:
                continue
            score = len(overlap) / len(query_tokens)
            scored.append(
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "content": doc["content"],
                    "score": round(score, 4),
                    "matched_words": sorted(overlap),
                }
            )
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[:top_k]
