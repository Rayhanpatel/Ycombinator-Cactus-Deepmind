"""
Web Ranker — optimistic scoring for web-scraped HVAC pages.

Given already-fetched web documents, produces a ranked list using:

    score = w_sim  * cosine(query, doc)
          + w_auth * authority(domain)
          + w_fresh * recency_decay(last_modified)
          + w_unc  * sqrt(ln(N + 1) / (n_source + 1))   ← UCB explore bonus
          - w_dup  * max_cosine(doc, existing_KB)

The UCB term is what makes the ranker "optimistic": sources we've seen
rarely get a confidence-interval boost so they surface before they've
earned a track record. Pair with an allowlist (authority map) so the
explore bonus doesn't drag in junk.

Scraping is intentionally *not* handled here — feed in `WebDoc` objects
from whatever fetcher you like (httpx, trafilatura, requests+bs4, etc.).
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from src.kb_engine import KBEngine, _cosine_similarity

logger = logging.getLogger(__name__)


# ── Authority map ────────────────────────────────────────────────
# Manufacturer support sites score highest; neutral-quality communities
# mid-range; unknown hosts fall through to 0.0 and must earn their place
# via cosine + UCB bonus.
DEFAULT_AUTHORITY: dict[str, float] = {
    # Manufacturer support — the gold standard for service manuals
    "support.movincool.com": 1.0,
    "movincool.com": 0.95,
    "carrier.com": 1.0,
    "trane.com": 1.0,
    "lennox.com": 1.0,
    "goodmanmfg.com": 1.0,
    "rheem.com": 1.0,
    "york.com": 1.0,
    "americanstandardair.com": 1.0,
    # Trade references / standards bodies
    "ashrae.org": 0.9,
    "achrnews.com": 0.75,
    "contractingbusiness.com": 0.7,
    # Community Q&A — useful signal but noisy
    "hvac-talk.com": 0.5,
    "reddit.com": 0.35,
    "stackexchange.com": 0.5,
    "youtube.com": 0.3,
}

# Default weights — tuned so that a perfect cosine match on an unknown
# domain still beats a weak match on a top-authority domain, but a
# strong manufacturer hit wins ties. Adjust in WebRanker(...).
DEFAULT_WEIGHTS = {
    "w_sim": 1.0,
    "w_auth": 0.30,
    "w_fresh": 0.15,
    "w_unc": 0.20,
    "w_dup": 0.40,
}

DEFAULT_FRESHNESS_HALF_LIFE_DAYS = 365.0


@dataclass
class WebDoc:
    """A single fetched web document to be ranked."""

    url: str
    text: str                               # cleaned body text (post-boilerplate strip)
    title: str = ""
    last_modified: Optional[float] = None   # unix timestamp; None → no freshness signal
    embedding: Optional[list[float]] = None # if pre-computed; otherwise filled lazily


@dataclass
class RankedDoc:
    doc: WebDoc
    score: float
    components: dict[str, float] = field(default_factory=dict)


class WebRanker:
    """
    Optimistic re-ranker for web-scraped pages.

    Stateful: persists per-domain visit counts to `state_file` so the UCB
    bonus works across runs. Delete the state file to reset exploration.
    """

    def __init__(
        self,
        kb_engine: Optional[KBEngine] = None,
        authority: Optional[dict[str, float]] = None,
        weights: Optional[dict[str, float]] = None,
        half_life_days: float = DEFAULT_FRESHNESS_HALF_LIFE_DAYS,
        state_file: str | Path = "kb/web_ranker_state.json",
    ):
        self.kb = kb_engine
        self.authority = {**DEFAULT_AUTHORITY, **(authority or {})}
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.half_life_days = half_life_days
        self.state_file = Path(state_file)
        self._source_counts: dict[str, int] = self._load_state()

        # Auto-extend the allowlist with domains already referenced in the KB.
        if self.kb is not None and self.kb.entries:
            self._seed_authority_from_kb()

    # ── public API ───────────────────────────────────────────────
    def rank(
        self,
        query: str,
        docs: list[WebDoc],
        top_k: Optional[int] = None,
    ) -> list[RankedDoc]:
        """Score every doc and return them sorted high→low."""
        if not docs:
            return []

        query_vec = self._embed(query) if self.kb is not None else None
        kb_vecs = self._kb_embeddings() if self.kb is not None else []

        total_visits = max(1, sum(self._source_counts.values()))
        ln_total = math.log(total_visits + 1)

        ranked: list[RankedDoc] = []
        for doc in docs:
            doc_vec = self._ensure_doc_embedding(doc)
            ranked.append(
                self._score_one(doc, doc_vec, query_vec, kb_vecs, ln_total)
            )

        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked[:top_k] if top_k else ranked

    def record_visit(self, url: str) -> None:
        """Increment the visit counter for a URL's domain and persist."""
        domain = _domain_of(url)
        if not domain:
            return
        self._source_counts[domain] = self._source_counts.get(domain, 0) + 1
        self._save_state()

    # ── scoring internals ────────────────────────────────────────
    def _score_one(
        self,
        doc: WebDoc,
        doc_vec: Optional[list[float]],
        query_vec: Optional[list[float]],
        kb_vecs: list[list[float]],
        ln_total: float,
    ) -> RankedDoc:
        domain = _domain_of(doc.url)

        sim = _cosine_similarity(query_vec, doc_vec) if (query_vec and doc_vec) else 0.0
        auth = self.authority.get(domain, 0.0)
        fresh = self._freshness(doc.last_modified)
        n_source = self._source_counts.get(domain, 0)
        ucb = math.sqrt(ln_total / (n_source + 1))
        dup = self._redundancy(doc_vec, kb_vecs) if doc_vec else 0.0

        w = self.weights
        total = (
            w["w_sim"] * sim
            + w["w_auth"] * auth
            + w["w_fresh"] * fresh
            + w["w_unc"] * ucb
            - w["w_dup"] * dup
        )

        return RankedDoc(
            doc=doc,
            score=total,
            components={
                "cosine": round(sim, 4),
                "authority": round(auth, 3),
                "freshness": round(fresh, 3),
                "ucb_bonus": round(ucb, 3),
                "redundancy": round(dup, 3),
                "domain": domain,
                "visits": n_source,
            },
        )

    def _freshness(self, last_modified: Optional[float]) -> float:
        if last_modified is None:
            return 0.5  # neutral — unknown age shouldn't help or hurt much
        age_days = max(0.0, (time.time() - last_modified) / 86400.0)
        return 0.5 ** (age_days / self.half_life_days)

    def _redundancy(self, doc_vec: list[float], kb_vecs: list[list[float]]) -> float:
        if not kb_vecs:
            return 0.0
        return max(_cosine_similarity(doc_vec, kv) for kv in kb_vecs)

    # ── embedding helpers ────────────────────────────────────────
    def _embed(self, text: str) -> Optional[list[float]]:
        if self.kb is None:
            return None
        model = self.kb._get_embed_model()
        if model is None:
            return None
        return model.encode(text, convert_to_numpy=True).tolist()

    def _ensure_doc_embedding(self, doc: WebDoc) -> Optional[list[float]]:
        if doc.embedding is not None:
            return doc.embedding
        body = (doc.title + "\n" + doc.text).strip()
        if not body:
            return None
        doc.embedding = self._embed(body)
        return doc.embedding

    def _kb_embeddings(self) -> list[list[float]]:
        if self.kb is None:
            return []
        return [e["embedding"] for e in self.kb.entries if e.get("embedding")]

    # ── authority seeding ────────────────────────────────────────
    def _seed_authority_from_kb(self) -> None:
        """Any domain already linked from a curated KB entry is trusted at 0.9."""
        for entry in self.kb.entries:
            for ref in entry.get("references", []) or []:
                url = ref.get("url") if isinstance(ref, dict) else ref
                domain = _domain_of(url or "")
                if domain and domain not in self.authority:
                    self.authority[domain] = 0.9

    # ── persistence ──────────────────────────────────────────────
    def _load_state(self) -> dict[str, int]:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file) as f:
                data = json.load(f)
            return {k: int(v) for k, v in data.get("source_counts", {}).items()}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"web_ranker: failed to load state ({e}); starting fresh")
            return {}

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump({"source_counts": self._source_counts}, f, indent=2)
        except OSError as e:
            logger.warning(f"web_ranker: failed to persist state ({e})")


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host
