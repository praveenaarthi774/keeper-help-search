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

from flask import Flask, request, jsonify, render_template, abort

from data_loader import load_documents, DatasetError
from search_engine import SemanticSearchEngine
from suggestions import SuggestionEngine
from articles import store as article_store

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Jinja filter: make URLs/emails clickable and highlight verify markers.
# The input is escaped first so it is safe to mark the result |safe.
# ---------------------------------------------------------------------------
import re as _re
from markupsafe import escape as _escape, Markup


@app.template_filter("linkify")
def linkify(text: str) -> Markup:
    safe = str(_escape(text))  # escape user/content text first (XSS-safe)

    # URLs -> anchor tags (keep a trailing '#', strip sentence punctuation).
    def _url(m):
        url = m.group(0)
        trail = ""
        while url and url[-1] in ".,);":
            trail = url[-1] + trail
            url = url[:-1]
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
            + trail
        )

    safe = _re.sub(r"https?://[^\s<]+", _url, safe)
    # Emails -> mailto.
    safe = _re.sub(
        r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
        lambda m: f'<a href="mailto:{m.group(0)}">{m.group(0)}</a>',
        safe,
    )
    # Highlight [VERIFY WITH ERICSSON ...] markers as a small badge.
    safe = _re.sub(
        r"\[VERIFY WITH ERICSSON[^\]]*\]",
        lambda m: f'<span class="verify">{m.group(0)}</span>',
        safe,
    )
    return Markup(safe)


# Topics shown as "Popular" on the home page.
POPULAR_SLUGS = [
    "keeper-login-instructions",
    "request-keeper-access",
    "password-recovery",
    "desktop-application-login-issues",
    "admin-approval-for-new-devices",
    "keeper-one-time-share",
]

# Map a document title (from the CSV) to its article slug, so search results
# can link to the right detailed article page. Titles that don't map just
# won't get a link.
TITLE_TO_SLUG = {
    "Keeper Login Instructions": "keeper-login-instructions",
    "Keeper Password Reset": "password-recovery",
    "Keeper Two-Factor Authentication": "two-factor-authentication",
    "Admin Approval for New Devices": "admin-approval-for-new-devices",
    "Keeper Access Request": "request-keeper-access",
    "Keeper Shared Folder Access": "shared-folder-access",
    "Keeper Desktop Application Login Issue": "desktop-application-login-issues",
    "Keeper Device Approval Pending": "pending-device-approval",
    "Keeper Desktop Application Update": "application-update-issues",
    "Keeper Account Transfer": "account-transfer",
    "Keeper One-Time Share": "keeper-one-time-share",
    "Keeper Secrets Manager Access": "keeper-secrets-manager",
    "Contact Keeper Support": "keeper-login-instructions",
}

# Search configuration.
# fastembed (bge-small) similarity scores run higher than TF-IDF: real
# matches land around 0.70-0.80, unrelated/gibberish around 0.40-0.48.
# 0.55 sits safely between, so irrelevant queries return no results.
TOP_K = 5
MIN_SCORE = 0.55

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
# Web pages
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        categories=article_store.all_categories(),
        popular=article_store.popular(POPULAR_SLUGS),
    )


@app.route("/categories", methods=["GET"])
def categories():
    return render_template(
        "categories.html",
        categories=article_store.all_categories(),
    )


@app.route("/category/<name>", methods=["GET"])
def category(name: str):
    meta = article_store.category_meta(name)
    if not meta:
        abort(404)
    return render_template(
        "category.html",
        category_name=name,
        category=meta,
        articles=article_store.in_category(name),
    )


@app.route("/article/<slug>", methods=["GET"])
def article(slug: str):
    art = article_store.get(slug)
    if not art:
        abort(404)
    # Resolve related slugs into {slug, title} for links.
    related = []
    for rslug in art.get("related", []):
        r = article_store.get(rslug)
        if r:
            related.append({"slug": r["slug"], "title": r["title"]})
    return render_template("article.html", a=art, related=related)


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


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

    # Attach a link to the detailed article page for each result (when known).
    for r in results:
        slug = TITLE_TO_SLUG.get(r["title"])
        r["article_url"] = f"/article/{slug}" if slug else None

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
