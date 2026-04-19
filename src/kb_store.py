"""
Knowledge Base store — loads kb/*.json at startup and serves keyword-scored
lookups for the query_kb tool.

The KB is small (10 entries) so we skip embeddings and use token-overlap
scoring: matches against tags, brand/model, and the symptom text.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(text.lower()) if t and len(t) > 1}


class KBStore:
    def __init__(self, kb_dir: Path):
        self._entries: list[dict[str, Any]] = []
        self._kb_dir = kb_dir

    def load(self) -> int:
        self._entries.clear()
        for path in sorted(self._kb_dir.glob("*.json")):
            try:
                with path.open() as f:
                    entry = json.load(f)
                entry["_tokens"] = (
                    _tokenize(" ".join(entry.get("tags", [])))
                    | _tokenize(entry.get("brand", ""))
                    | _tokenize(entry.get("model", ""))
                    | _tokenize(entry.get("equipment_type", ""))
                    | _tokenize(entry.get("symptom", ""))
                )
                self._entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to load KB entry {path.name}: {e}")
        logger.info(f"KB loaded: {len(self._entries)} entries from {self._kb_dir}")
        return len(self._entries)

    def search(
        self,
        query: str,
        equipment_model: str | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        model_tokens = _tokenize(equipment_model) if equipment_model else set()

        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in self._entries:
            score = 0
            entry_tags = {t.lower() for t in entry.get("tags", [])}

            for tok in query_tokens:
                if tok in entry_tags:
                    score += 3
                if tok in entry["_tokens"]:
                    score += 1
                if tok in entry.get("brand", "").lower():
                    score += 2
                if tok in entry.get("model", "").lower():
                    score += 2

            for tok in model_tokens:
                if tok in entry["_tokens"]:
                    score += 5

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {k: v for k, v in entry.items() if not k.startswith("_")} | {"score": score}
            for score, entry in scored[:top_k]
        ]

    @property
    def entry_count(self) -> int:
        return len(self._entries)


_GLOBAL_STORE: KBStore | None = None


def get_kb_store() -> KBStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        repo_root = Path(__file__).resolve().parent.parent
        _GLOBAL_STORE = KBStore(repo_root / "kb")
        _GLOBAL_STORE.load()
    return _GLOBAL_STORE
