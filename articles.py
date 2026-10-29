"""
articles.py
===========

Loads the structured knowledge-base content from data/articles.json and
provides helpers to look articles up by slug or by category.

The JSON holds the full article content (the 10 sections) plus the category
definitions (icon + description). This keeps the content in one place and lets
a single Jinja template render any article.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "articles.json"
)


class _Store:
    def __init__(self) -> None:
        with open(_DATA_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.categories: Dict[str, Dict] = data["categories"]
        self.articles: List[Dict] = data["articles"]
        self._by_slug = {a["slug"]: a for a in self.articles}

    def all_categories(self) -> List[Dict]:
        """Return categories with their article counts, for the home page."""
        out = []
        for name, meta in self.categories.items():
            arts = self.in_category(name)
            out.append(
                {
                    "name": name,
                    "icon": meta.get("icon", "📄"),
                    "description": meta.get("description", ""),
                    "count": len(arts),
                }
            )
        return out

    def in_category(self, name: str) -> List[Dict]:
        return [a for a in self.articles if a["category"] == name]

    def get(self, slug: str) -> Dict | None:
        return self._by_slug.get(slug)

    def category_meta(self, name: str) -> Dict | None:
        return self.categories.get(name)

    def popular(self, slugs: List[str]) -> List[Dict]:
        return [self._by_slug[s] for s in slugs if s in self._by_slug]


# Single shared instance, loaded once.
store = _Store()
