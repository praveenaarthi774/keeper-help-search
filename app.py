"""
app.py
======

Flask web application and REST API for the semantic search system.

Routes:
- GET  /            -> HTML search page (templates/index.html)
- POST /search      -> JSON API: { "query": "..." } -> matching documents
- GET  /health      -> simple health check

The embedding model and FAISS index are built ONCE at startup and reused for
every request, so searches are fast.
"""

from __future__ import annotations

from flask import Flask, request, jsonify, render_template

from data_loader import load_documents, DatasetError
from search_engine import SemanticSearchEngine
from suggestions import SuggestionEngine

app = Flask(__name__)

# Search configuration.
TOP_K = 5
MIN_SCORE = 0.30  # cosine-similarity threshold; tune higher to be stricter.

# Global engines, initialised at startup.
engine: SemanticSearchEngine | None = None
suggester: SuggestionEngine | None = None


def init_engine() -> None:
    """Load documents and build the FAISS index once at startup."""
    global engine, suggester
    documents = load_documents()
    engine = SemanticSearchEngine()
    engine.build_index(documents)
    suggester = SuggestionEngine(documents)
    print(f"Search engine ready with {len(documents)} documents.")


# ---------------------------------------------------------------------------
# Web page
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.route("/search", methods=["POST"])
def search():
    """
    Semantic search endpoint.

    Request JSON:  { "query": "I forgot my password" }
    Response JSON: { "query": ..., "count": N, "results": [ ... ] }
    """
    if engine is None:
        return jsonify({"error": "Search engine is not ready."}), 503

    # Validate the request body.
    data = request.get_json(silent=True)
    if not data or "query" not in data:
        return jsonify({"error": "Request must be JSON with a 'query' field."}), 400

    query = str(data.get("query", "")).strip()
    if not query:
        return jsonify({"error": "Query cannot be empty."}), 400

    # Optional overrides from the request.
    top_k = int(data.get("top_k", TOP_K))
    min_score = float(data.get("min_score", MIN_SCORE))

    try:
        results = engine.search(query, top_k=top_k, min_score=min_score)
    except Exception as exc:
        return jsonify({"error": f"Search failed: {exc}"}), 500

    message = None
    if not results:
        message = "No sufficiently relevant documents were found for your query."

    return jsonify(
        {
            "query": query,
            "count": len(results),
            "results": results,
            "message": message,
        }
    )


# ---------------------------------------------------------------------------
# Suggestions (typo-tolerant autocomplete)
# ---------------------------------------------------------------------------
@app.route("/suggest", methods=["GET"])
def suggest():
    """
    Return query suggestions for what the user is typing.

    Example: GET /suggest?q=pasword
    Response: { "suggestions": ["Keeper Password Reset", ...] }

    Handles misspellings via fuzzy matching, so "pasword" still suggests
    "Keeper Password Reset".
    """
    if suggester is None:
        return jsonify({"suggestions": []})

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"suggestions": []})

    results = suggester.suggest(query, limit=6)
    return jsonify({"suggestions": results})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    ready = engine is not None
    return jsonify({"status": "ok" if ready else "initialising", "ready": ready})


# Build the engine at import time so a production server (gunicorn) also
# initialises it. This runs once when the app starts.
try:
    init_engine()
except DatasetError as exc:
    raise SystemExit(f"Failed to load dataset: {exc}")


if __name__ == "__main__":
    # Local run. On Render, gunicorn serves the `app` object instead and the
    # PORT is provided via the environment.
    import os

    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
