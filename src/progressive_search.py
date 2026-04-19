"""
Progressive Search — escalate retrieval depth only when the cheaper tiers
haven't solved the user's problem.

Default path:
  1. Tier 0 (KB_ONLY)         — curated JSON, local only, ~zero cost
  2. Tier 1 (FORUMS_SHALLOW)   — KB + Reddit (depth 2, 3 submissions/sub)
  3. Tier 2 (FORUMS_DEEP)      — KB + Reddit (depth 6, 10 submissions/sub,
                                  with author-age lookup for better expertise
                                  scoring)

Escalation triggers:
  - Explicit: user message contains an "unresolved" phrase ("didn't work",
    "still broken", "no luck", …) — caller invokes `maybe_escalate()`.
  - Manual: caller invokes `escalate()` for whatever reason (low confidence,
    follow-up on same equipment cluster, etc.).

Dedup: results surfaced in a prior tier are filtered out on escalation so
the user always sees *new* candidates, not a re-ranked re-run of the
same rejected answers.

A web-manual scraper tier will slot in between KB_ONLY and FORUMS_SHALLOW
when it exists — pass a `web_scraper` callable and extend `TIER_CONFIG`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Iterator, Optional

from src.kb_engine import KBEngine
from src.web_ranker import RankedDoc, WebDoc, WebRanker

logger = logging.getLogger(__name__)


class SearchTier(IntEnum):
    KB_ONLY = 0
    FORUMS_SHALLOW = 1
    FORUMS_DEEP = 2


# Per-tier retrieval knobs. Keep these declarative so adding a tier is a
# config edit, not a control-flow rewrite.
TIER_CONFIG: dict[SearchTier, dict] = {
    SearchTier.KB_ONLY: {
        "include_reddit": False,
        "reddit_limit": 0,
        "reddit_depth": 0,
        "fetch_author_age": False,
    },
    SearchTier.FORUMS_SHALLOW: {
        "include_reddit": True,
        "reddit_limit": 3,
        "reddit_depth": 2,
        "fetch_author_age": False,
    },
    SearchTier.FORUMS_DEEP: {
        "include_reddit": True,
        "reddit_limit": 10,
        "reddit_depth": 6,
        "fetch_author_age": True,
    },
}


# Phrases a user says when the prior answer didn't solve it. Conservative
# list — false positives cause premature escalation and unnecessary cost.
UNRESOLVED_PATTERNS: tuple[str, ...] = (
    "didn't work",
    "did not work",
    "still broken",
    "still not working",
    "still not fixed",
    "no luck",
    "tried that",
    "doesn't help",
    "does not help",
    "same issue",
    "same problem",
    "nothing changed",
    "what else",
    "other options",
    "anything else",
    "any other ideas",
    "hasn't solved",
    "not solving",
    "not fixing",
    "dig deeper",
)


def is_unresolved_signal(text: str) -> bool:
    """True when the user's message reads as 'that didn't solve it'."""
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in UNRESOLVED_PATTERNS)


@dataclass
class SearchSession:
    """Per-conversation retrieval state — in-memory, not persisted."""
    original_query: str
    tier: SearchTier = SearchTier.KB_ONLY
    shown_urls: set[str] = field(default_factory=set)
    query_history: list[str] = field(default_factory=list)
    escalations: int = 0


class ProgressiveSearcher:
    """
    Orchestrates tiered retrieval. Start cheap; escalate only when the
    cheaper tier didn't resolve the user's problem.
    """

    def __init__(
        self,
        kb_engine: KBEngine,
        ranker: WebRanker,
        reddit_fetcher=None,
        web_scraper: Optional[Callable[[str], list[WebDoc]]] = None,
    ):
        self.kb = kb_engine
        self.ranker = ranker
        self.reddit = reddit_fetcher
        self.scraper = web_scraper
        # KB entries don't live on a real domain. Give the synthetic host
        # top-tier authority so curated entries aren't unfairly demoted.
        self.ranker.authority.setdefault("kb.local", 0.95)

    # ── session lifecycle ────────────────────────────────────────
    def start_session(self, query: str) -> SearchSession:
        return SearchSession(original_query=query)

    def escalate(self, session: SearchSession) -> SearchTier:
        """Bump the tier by one, capped at the deepest tier."""
        if session.tier < SearchTier.FORUMS_DEEP:
            session.tier = SearchTier(int(session.tier) + 1)
            session.escalations += 1
            logger.info(f"🔎 progressive: escalated to {session.tier.name}")
        return session.tier

    def maybe_escalate(self, session: SearchSession, user_message: str) -> bool:
        """
        Inspect a user follow-up and escalate if it reads as unresolved.
        Returns True when the tier was bumped.
        """
        if is_unresolved_signal(user_message):
            session.query_history.append(user_message)
            prev = session.tier
            self.escalate(session)
            return session.tier != prev
        return False

    # ── retrieval ────────────────────────────────────────────────
    def search(
        self,
        session: SearchSession,
        top_k: int = 5,
        query_override: Optional[str] = None,
    ) -> list[RankedDoc]:
        """
        Gather candidate docs for the current tier, drop anything the user
        has already seen, rank via WebRanker, and remember what we showed
        so the next escalation shows fresh results.
        """
        cfg = TIER_CONFIG[session.tier]
        query = query_override or session.original_query

        docs: list[WebDoc] = list(self._kb_docs())

        if self.scraper is not None:
            try:
                docs.extend(self.scraper(query))
            except Exception as e:
                logger.warning(f"progressive: web scraper failed: {e}")

        if cfg["include_reddit"] and self.reddit is not None and getattr(
            self.reddit, "is_available", False
        ):
            docs.extend(self._fetch_reddit(query, cfg))

        # Dedup: never re-show a URL the user has already rejected.
        docs = [d for d in docs if d.url not in session.shown_urls]

        ranked = self.ranker.rank(query, docs, top_k=top_k)

        for r in ranked:
            session.shown_urls.add(r.doc.url)

        return ranked

    # ── source adapters ──────────────────────────────────────────
    def _kb_docs(self) -> Iterator[WebDoc]:
        """
        Convert each KB entry into a WebDoc so the unified ranker can score
        it alongside web/forum results. The embedding is already computed
        (see src/embeddings.py) so no re-encoding happens.
        """
        for entry in self.kb.entries:
            yield WebDoc(
                url=_kb_representative_url(entry),
                title=entry.get("title", ""),
                text=_kb_search_text(entry),
                embedding=entry.get("embedding"),
            )

    def _fetch_reddit(self, query: str, cfg: dict) -> list[WebDoc]:
        prev_age = getattr(self.reddit, "fetch_author_age", False)
        self.reddit.fetch_author_age = cfg["fetch_author_age"]
        try:
            return self.reddit.search(
                query,
                limit=cfg["reddit_limit"],
                comment_depth_limit=cfg["reddit_depth"],
            )
        finally:
            self.reddit.fetch_author_age = prev_age


# ── KB → WebDoc helpers ──────────────────────────────────────────
def _kb_representative_url(entry: dict) -> str:
    """Pick a URL that represents the KB entry's authority source."""
    refs = entry.get("references", []) or []
    if refs:
        ref = refs[0]
        url = ref.get("url") if isinstance(ref, dict) else ref
        if url:
            return url
    return f"https://kb.local/{entry.get('id', 'unknown')}"


def _kb_search_text(entry: dict) -> str:
    """Mirror src/embeddings.build_search_text so ranking text matches what
    was embedded."""
    parts = [
        entry.get("brand", ""),
        entry.get("model", ""),
        entry.get("symptom", ""),
        entry.get("diagnosis", ""),
        " ".join(entry.get("tags", []) or []),
    ]
    return " ".join(p for p in parts if p).strip()
