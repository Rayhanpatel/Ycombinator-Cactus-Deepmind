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
            # The kb_index.json is a sidecar that the teammate's embeddings
            # pipeline produces; it's not a real entry, skip it.
            if path.name == "kb_index.json":
                continue
            try:
                with path.open() as f:
                    entry = json.load(f)
                # Token bag is the union of every searchable text field we
                # know about across BOTH KB schemas:
                # - "flat" schema (original): brand, model, equipment_type,
                #   symptom (str), tags[]
                # - "rich" schema (teammate's MovinCool): manufacturer,
                #   category, symptoms[], common_faults[],
                #   common_applications[], title
                def _pull_list(key: str) -> str:
                    v = entry.get(key)
                    if isinstance(v, list):
                        return " ".join(str(x) for x in v)
                    return ""

                tokens = set()
                for s in (
                    entry.get("brand"),
                    entry.get("manufacturer"),
                    entry.get("model"),
                    entry.get("equipment_type"),
                    entry.get("category"),
                    entry.get("title"),
                    entry.get("symptom"),
                    entry.get("diagnosis"),
                    _pull_list("tags"),
                    _pull_list("symptoms"),
                    _pull_list("common_faults"),
                    _pull_list("common_applications"),
                ):
                    if s:
                        tokens |= _tokenize(str(s))
                entry["_tokens"] = tokens
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
            # Handle both "brand" (flat schema) and "manufacturer" (rich schema).
            brand_l = (entry.get("brand") or entry.get("manufacturer") or "").lower()

            for tok in query_tokens:
                if tok in entry_tags:
                    score += 3
                if tok in entry["_tokens"]:
                    score += 1
                if tok in brand_l:
                    score += 2
                if tok in entry.get("model", "").lower():
                    score += 2

            for tok in model_tokens:
                if tok in entry["_tokens"]:
                    score += 5

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Strip fields that shouldn't reach the LLM as tool-result content:
        # - keys starting with `_` are internal cache (e.g. `_tokens`, `_todo`)
        # - `embedding` is a 384-dim vector (~7500 chars per entry) added by
        #   the teammate's offline pipeline; we don't use it and dumping it
        #   into the model's context on every query_kb call bloats pass-2
        #   prefill by ~7500 tokens per hit and has triggered Cactus crashes.
        _SKIP = {"embedding", "symptoms_embedding"}
        return [
            {k: v for k, v in entry.items() if not k.startswith("_") and k not in _SKIP}
            | {"score": score}
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
