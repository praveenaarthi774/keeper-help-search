"""
suggestions.py
==============

Builds and serves query SUGGESTIONS for the search box, with TYPO tolerance.

Two jobs:
1. Suggest relevant example questions as the user types (autocomplete).
2. Tolerate misspellings ("pasword rest" -> "Keeper Password Reset") using
   fuzzy matching, so the user still finds the right suggestion.

Why difflib? It's part of Python's standard library (no extra install) and
is good enough for short help-desk queries. It compares how similar two
strings are, which lets us match even when letters are wrong.

The suggestion list is built from:
- each document's title, and
- a few hand-written example questions per category (natural phrasing),
plus auto-generated phrasings so the list covers common wording.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Dict


# A few natural example questions mapped to the kind of article they lead to.
# These make suggestions feel human ("how do I ..." rather than just titles).
EXAMPLE_QUESTIONS = [
    "How do I log in to Keeper?",
    "How do I sign in to the Keeper vault?",
    "I forgot my Keeper password",
    "How do I reset my Keeper password?",
    "I cannot sign in to Keeper",
    "The Keeper desktop app will not open",
    "The desktop application will not let me sign in",
    "How do I update the Keeper desktop app?",
    "I need approval for a new device",
    "My new laptop needs admin approval for Keeper",
    "My device approval is still pending",
    "How do I request access to Keeper?",
    "How do I get access to the password vault?",
    "I cannot open a shared folder in Keeper",
    "How do I access a shared folder?",
    "How do I set up two-factor authentication?",
    "I cannot complete two-factor verification",
    "How do I transfer a Keeper account?",
    "How do I transfer vault records to another user?",
    "How do I share a password with someone without a Keeper account?",
    "How do I use Keeper One-Time Share?",
    "What is Keeper Secrets Manager?",
    "How do I get access to Keeper Secrets Manager?",
]


# Common abbreviations / synonyms users type -> the real words they mean.
# Expanding these lets "2fa" match "two-factor authentication", etc.
ALIASES = {
    "2fa": "two factor authentication",
    "mfa": "two factor authentication",
    "otp": "two factor authentication code",
    "pwd": "password",
    "pass": "password",
    "login": "log in sign in",
    "signin": "sign in log in",
    "app": "desktop application",
    "pc": "desktop computer",
    "sso": "enterprise sso single sign on",
    "ksm": "keeper secrets manager",
}


def _normalize(text: str) -> str:
    """Lowercase and collapse spaces for comparison."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _expand_aliases(query: str) -> str:
    """Replace known abbreviations with their full meaning before matching."""
    words = _normalize(query).split()
    expanded = [ALIASES.get(w, w) for w in words]
    return " ".join(expanded)


def _similarity(a: str, b: str) -> float:
    """Return a 0-1 similarity ratio between two strings (typo tolerant)."""
    return SequenceMatcher(None, a, b).ratio()


class SuggestionEngine:
    """Provides typo-tolerant query suggestions from titles + example questions."""

    def __init__(self, documents: List[Dict]) -> None:
        # Build the master suggestion list: titles + example questions.
        titles = [d["title"] for d in documents]
        self.suggestions: List[str] = EXAMPLE_QUESTIONS + titles

        # De-duplicate while preserving order.
        seen = set()
        unique = []
        for s in self.suggestions:
            key = _normalize(s)
            if key not in seen:
                seen.add(key)
                unique.append(s)
        self.suggestions = unique

        # Pre-normalize once, and index the words for fuzzy word matching.
        self._norm = [_normalize(s) for s in self.suggestions]

    def suggest(self, query: str, limit: int = 6) -> List[str]:
        """
        Return up to `limit` suggestions ranked by relevance to `query`.

        Scoring blends three signals so it works for partial typing AND typos:
        1. Substring match  -> the typed text appears in the suggestion.
        2. Word overlap     -> shared words (fuzzy, so misspellings count).
        3. Whole-string similarity -> overall closeness (catches typos).
        """
        q = _normalize(query)
        if not q:
            return []

        # Expand abbreviations (2fa -> two factor authentication) so they match.
        q = _expand_aliases(q)
        q_words = q.split()
        scored = []

        for original, norm in zip(self.suggestions, self._norm):
            score = 0.0

            # 1. Strong boost if the typed text is a direct substring.
            if q in norm:
                score += 1.0

            # 2. Fuzzy word overlap: for each typed word, find its best
            #    matching word in the suggestion. This handles misspellings
            #    like "pasword" ~ "password".
            norm_words = norm.split()
            if norm_words:
                word_score = 0.0
                for qw in q_words:
                    best = max((_similarity(qw, nw) for nw in norm_words), default=0.0)
                    if best >= 0.7:          # count only close matches
                        word_score += best
                score += word_score / max(len(q_words), 1)

            # 3. Overall string similarity (catches whole-phrase typos).
            score += 0.5 * _similarity(q, norm)

            if score > 0.25:                 # drop clearly irrelevant ones
                scored.append((score, original))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]


if __name__ == "__main__":
    # Quick self-test with typos.
    from data_loader import load_documents

    eng = SuggestionEngine(load_documents())
    for q in ["pasword", "pasword rest", "cant login", "shred folder", "2fa", "new divice"]:
        print(f"\nQuery: {q!r}")
        for s in eng.suggest(q):
            print("   ->", s)
