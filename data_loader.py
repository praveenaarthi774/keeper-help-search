"""
data_loader.py
==============

Loads and validates the support document dataset from a CSV file.

Responsibilities:
- Read documents from `data/documents.csv` using pandas.
- Validate that required columns exist and rows are not empty.
- Return a clean list of document dictionaries for the search engine.
"""

from __future__ import annotations

import os
from typing import List, Dict

import pandas as pd

# Columns every document row must have.
REQUIRED_COLUMNS = ["id", "title", "category", "content"]

# Default dataset path (relative to this file, so it works from anywhere).
DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "documents.csv"
)


class DatasetError(Exception):
    """Raised when the dataset is missing, empty, or malformed."""


def load_documents(path: str | None = None) -> List[Dict]:
    """
    Load and validate documents from a CSV file.

    Returns a list of dicts, each with keys: id, title, category, content.
    Raises DatasetError on any problem so callers can handle it cleanly.
    """
    path = path or DEFAULT_DATA_PATH

    # 1. File must exist.
    if not os.path.exists(path):
        raise DatasetError(f"Dataset file not found: {path}")

    # 2. Read the CSV.
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - pandas raises many types
        raise DatasetError(f"Could not read CSV file: {exc}") from exc

    # 3. Must have rows.
    if df.empty:
        raise DatasetError("Dataset is empty - no documents found.")

    # 4. Must have all required columns.
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DatasetError(f"Dataset is missing required columns: {missing}")

    # 5. Drop rows where title or content is blank, then validate.
    df = df.fillna("")
    documents: List[Dict] = []
    for _, row in df.iterrows():
        title = str(row["title"]).strip()
        content = str(row["content"]).strip()
        if not title or not content:
            # Skip incomplete rows rather than crash the whole load.
            continue
        documents.append(
            {
                "id": int(row["id"]) if str(row["id"]).strip().isdigit() else row["id"],
                "title": title,
                "category": str(row["category"]).strip(),
                "content": content,
            }
        )

    if not documents:
        raise DatasetError("No valid documents after validation.")

    return documents


if __name__ == "__main__":
    # Quick self-test when run directly.
    docs = load_documents()
    print(f"Loaded {len(docs)} documents.")
    print("First document:", docs[0]["title"])
