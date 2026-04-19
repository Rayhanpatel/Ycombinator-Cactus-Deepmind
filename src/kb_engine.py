"""
KB Engine — Knowledge Base search with cosine similarity over MiniLM embeddings.

Loads pre-computed embeddings from kb/kb_index.json. Supports:
  - Semantic search via cosine similarity (requires sentence-transformers for query embedding)
  - Tag-based fallback search (no model needed)
  - Model/brand filtering

Usage:
    from src.kb_engine import KBEngine
    engine = KBEngine()
    engine.load()
    results = engine.search("capacitor short cycling Carrier", top_k=3)
"""

import json
import math
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Pure Python — no numpy needed."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class KBEngine:
    """Knowledge base search engine with embedding-based and tag-based retrieval."""

    def __init__(self, kb_dir: str = "kb", index_file: str = "kb/kb_index.json"):
        self.kb_dir = Path(kb_dir)
        self.index_file = Path(index_file)
        self.entries: list[dict] = []
        self._embed_model = None
        self._embeddings_available = False

    def load(self) -> None:
        """Load all KB entries. Prefer the pre-built index; fall back to individual files."""
        if self.index_file.exists():
            with open(self.index_file) as f:
                data = json.load(f)
                self.entries = data.get("entries", data) if isinstance(data, dict) else data
            # Check if embeddings are baked in
            if self.entries and "embedding" in self.entries[0]:
                self._embeddings_available = True
            logger.info(
                f"✅ Loaded {len(self.entries)} KB entries from index "
                f"(embeddings: {'yes' if self._embeddings_available else 'no'})"
            )
        else:
            # Fall back to loading individual JSON files
            self.entries = []
            for json_file in sorted(self.kb_dir.glob("*.json")):
                if json_file.name == "kb_index.json":
                    continue
                with open(json_file) as f:
                    self.entries.append(json.load(f))
            self._embeddings_available = any("embedding" in e for e in self.entries)
            logger.info(
                f"✅ Loaded {len(self.entries)} KB entries from individual files "
                f"(embeddings: {'yes' if self._embeddings_available else 'no'})"
            )

    def _get_embed_model(self):
        """Lazy-load the sentence-transformers model for query embedding."""
        if self._embed_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("✅ Loaded MiniLM embedding model for query encoding")
            except ImportError:
                logger.warning(
                    "⚠️  sentence-transformers not installed — falling back to tag search"
                )
                return None
        return self._embed_model

    def _embed_query(self, query: str) -> Optional[list[float]]:
        """Embed a query string. Returns None if model unavailable."""
        model = self._get_embed_model()
        if model is None:
            return None
        embedding = model.encode(query, convert_to_numpy=True)
        return embedding.tolist()

    def search(
        self,
        query: str,
        equipment_model: Optional[str] = None,
        top_k: int = 3,
    ) -> list[dict]:
        """
        Search the KB. Uses cosine similarity if embeddings are available,
        otherwise falls back to tag/text matching.

        Returns top-k results with similarity scores.
        """
        if not self.entries:
            return []

        # Filter by equipment model if provided
        candidates = self.entries
        if equipment_model:
            model_lower = equipment_model.lower()
            filtered = [
                e for e in candidates
                if model_lower in e.get("model", "").lower()
                or model_lower in e.get("id", "").lower()
            ]
            if filtered:
                candidates = filtered

        # Try semantic search first
        if self._embeddings_available:
            query_embedding = self._embed_query(query)
            if query_embedding is not None:
                return self._semantic_search(query_embedding, candidates, top_k)

        # Fall back to tag/text matching
        return self._tag_search(query, candidates, top_k)

    def _semantic_search(
        self,
        query_embedding: list[float],
        candidates: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Rank candidates by cosine similarity to the query embedding."""
        scored = []
        for entry in candidates:
            entry_embedding = entry.get("embedding")
            if entry_embedding is None:
                continue
            score = _cosine_similarity(query_embedding, entry_embedding)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, entry in scored[:top_k]:
            result = {k: v for k, v in entry.items() if k != "embedding"}
            result["similarity_score"] = round(score, 4)
            results.append(result)

        return results

    def _tag_search(
        self,
        query: str,
        candidates: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Simple keyword/tag matching fallback — no model needed."""
        query_words = set(query.lower().split())

        scored = []
        for entry in candidates:
            # Build searchable text from tags + symptom + diagnosis + brand + model
            searchable_parts = []
            searchable_parts.extend(entry.get("tags", []))
            searchable_parts.append(entry.get("symptom", ""))
            searchable_parts.append(entry.get("diagnosis", ""))
            searchable_parts.append(entry.get("brand", ""))
            searchable_parts.append(entry.get("model", ""))
            searchable_text = " ".join(searchable_parts).lower()

            # Count matching words
            matches = sum(1 for word in query_words if word in searchable_text)
            if matches > 0:
                # Normalize by query length for a rough "score"
                score = matches / len(query_words) if query_words else 0
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, entry in scored[:top_k]:
            result = {k: v for k, v in entry.items() if k != "embedding"}
            result["similarity_score"] = round(score, 4)
            result["match_type"] = "tag"
            results.append(result)

        return results

    def get_entry_by_id(self, entry_id: str) -> Optional[dict]:
        """Look up a KB entry by its ID."""
        for entry in self.entries:
            if entry.get("id") == entry_id:
                return entry
        return None
