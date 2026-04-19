"""Tests for src.progressive_search — no network, no model."""

from pathlib import Path

import pytest

from src.progressive_search import (
    ProgressiveSearcher,
    SearchSession,
    SearchTier,
    TIER_CONFIG,
    _kb_representative_url,
    _kb_search_text,
    is_unresolved_signal,
)
from src.web_ranker import WebDoc, WebRanker


# ── tiny test doubles ────────────────────────────────────────────
class FakeKB:
    """Duck-types the bits of KBEngine that ProgressiveSearcher touches."""
    def __init__(self, entries):
        self.entries = entries

    def _get_embed_model(self):
        return None  # suppress real model load


class FakeReddit:
    def __init__(self, docs):
        self._docs = docs
        self.is_available = True
        self.fetch_author_age = False
        self.last_kwargs = None

    def search(self, query, limit, comment_depth_limit):
        self.last_kwargs = {
            "query": query,
            "limit": limit,
            "depth": comment_depth_limit,
            "age": self.fetch_author_age,
        }
        return list(self._docs)


@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    return tmp_path / "ranker_state.json"


@pytest.fixture
def kb_entry():
    return {
        "id": "movincool_climate_pro_x14",
        "title": "MovinCool Climate Pro X14",
        "brand": "MovinCool",
        "model": "Climate Pro X14",
        "symptom": "condensate overflow",
        "diagnosis": "pump blockage",
        "tags": ["portable", "spot cooler"],
        "references": [{"url": "https://support.movincool.com/x14"}],
        "embedding": [1.0, 0.0, 0.0],
    }


@pytest.fixture
def searcher(tmp_state, kb_entry):
    kb = FakeKB(entries=[kb_entry])
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    return ProgressiveSearcher(kb_engine=kb, ranker=ranker)


# ── unresolved-signal classifier ─────────────────────────────────
@pytest.mark.parametrize("phrase", [
    "that didn't work",
    "still broken after swapping the cap",
    "no luck, same issue",
    "tried that already",
    "any other ideas?",
    "dig deeper please",
])
def test_unresolved_phrases_detected(phrase):
    assert is_unresolved_signal(phrase) is True


@pytest.mark.parametrize("phrase", [
    "thanks, that worked",
    "cool, any idea what caused it?",
    "",
    "how much does a new pump cost",
])
def test_neutral_phrases_not_detected(phrase):
    assert is_unresolved_signal(phrase) is False


# ── escalation ───────────────────────────────────────────────────
def test_start_session_defaults_to_tier_zero(searcher):
    s = searcher.start_session("X14 overflow")
    assert s.tier == SearchTier.KB_ONLY
    assert s.escalations == 0


def test_escalate_bumps_one_tier(searcher):
    s = searcher.start_session("q")
    assert searcher.escalate(s) == SearchTier.FORUMS_SHALLOW
    assert searcher.escalate(s) == SearchTier.FORUMS_DEEP
    # Capped at the deepest tier
    assert searcher.escalate(s) == SearchTier.FORUMS_DEEP
    assert s.escalations == 2


def test_maybe_escalate_only_on_unresolved_signal(searcher):
    s = searcher.start_session("q")
    assert searcher.maybe_escalate(s, "thanks that worked") is False
    assert s.tier == SearchTier.KB_ONLY
    assert searcher.maybe_escalate(s, "didn't work, any other ideas?") is True
    assert s.tier == SearchTier.FORUMS_SHALLOW


# ── KB → WebDoc conversion ───────────────────────────────────────
def test_kb_representative_url_prefers_first_reference(kb_entry):
    assert _kb_representative_url(kb_entry) == "https://support.movincool.com/x14"


def test_kb_representative_url_falls_back_to_synthetic():
    entry = {"id": "no_refs"}
    assert _kb_representative_url(entry) == "https://kb.local/no_refs"


def test_kb_search_text_includes_all_signal_fields(kb_entry):
    text = _kb_search_text(kb_entry)
    assert "MovinCool" in text and "condensate overflow" in text and "portable" in text


def test_kb_local_gets_authority(searcher):
    # ProgressiveSearcher seeds kb.local authority on construction.
    assert searcher.ranker.authority.get("kb.local") == 0.95


# ── tiered search behavior ───────────────────────────────────────
def test_tier_zero_skips_reddit(searcher, tmp_state):
    """KB_ONLY must not touch the reddit fetcher, even if one is attached."""
    reddit = FakeReddit(docs=[])
    searcher.reddit = reddit
    s = searcher.start_session("X14 overflow")
    searcher.search(s, top_k=5)
    assert reddit.last_kwargs is None  # never called


def test_forums_shallow_uses_configured_limits(kb_entry, tmp_state):
    kb = FakeKB(entries=[kb_entry])
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    reddit_doc = WebDoc(
        url="https://reddit.com/r/HVAC/comments/abc/_/x",
        text="try the pump float",
        author="pro",
        author_flair="Certified HVAC-Pro",
        depth=2, parent_upvotes=50,
    )
    reddit = FakeReddit(docs=[reddit_doc])
    searcher = ProgressiveSearcher(kb, ranker, reddit_fetcher=reddit)

    s = searcher.start_session("X14 overflow")
    searcher.escalate(s)
    ranked = searcher.search(s, top_k=5)

    cfg = TIER_CONFIG[SearchTier.FORUMS_SHALLOW]
    assert reddit.last_kwargs == {
        "query": "X14 overflow",
        "limit": cfg["reddit_limit"],
        "depth": cfg["reddit_depth"],
        "age": cfg["fetch_author_age"],
    }
    urls = [r.doc.url for r in ranked]
    assert "https://reddit.com/r/HVAC/comments/abc/_/x" in urls


def test_forums_deep_toggles_author_age(kb_entry, tmp_state):
    kb = FakeKB(entries=[kb_entry])
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    reddit = FakeReddit(docs=[])
    searcher = ProgressiveSearcher(kb, ranker, reddit_fetcher=reddit)

    s = searcher.start_session("q")
    searcher.escalate(s); searcher.escalate(s)
    searcher.search(s)

    assert reddit.last_kwargs["age"] is True
    # And it was restored afterwards (non-leaky).
    assert reddit.fetch_author_age is False


def test_dedup_across_escalations(kb_entry, tmp_state):
    """A KB entry surfaced at tier 0 shouldn't reappear after escalation."""
    kb = FakeKB(entries=[kb_entry])
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    reddit_doc = WebDoc(
        url="https://reddit.com/r/HVAC/comments/abc/_/x",
        text="new answer",
        depth=1, parent_upvotes=50,
    )
    reddit = FakeReddit(docs=[reddit_doc])
    searcher = ProgressiveSearcher(kb, ranker, reddit_fetcher=reddit)

    s = searcher.start_session("X14 overflow")
    first = searcher.search(s)
    kb_url = "https://support.movincool.com/x14"
    assert any(r.doc.url == kb_url for r in first)

    searcher.escalate(s)
    second = searcher.search(s)
    assert all(r.doc.url != kb_url for r in second)
    assert any(r.doc.url.startswith("https://reddit.com") for r in second)


def test_scraper_is_called_when_provided(searcher, kb_entry):
    calls = []
    def fake_scraper(q: str) -> list[WebDoc]:
        calls.append(q)
        return [WebDoc(url="https://carrier.com/tsb/123", text="scraped manual note")]
    searcher.scraper = fake_scraper

    s = searcher.start_session("X14 overflow")
    ranked = searcher.search(s)

    assert calls == ["X14 overflow"]
    assert any(r.doc.url == "https://carrier.com/tsb/123" for r in ranked)


def test_reddit_unavailable_is_safe(kb_entry, tmp_state):
    class UnavailableReddit:
        is_available = False
        fetch_author_age = False
        def search(self, *a, **kw):
            raise AssertionError("should not be called")

    kb = FakeKB(entries=[kb_entry])
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    searcher = ProgressiveSearcher(kb, ranker, reddit_fetcher=UnavailableReddit())

    s = searcher.start_session("q")
    searcher.escalate(s)
    ranked = searcher.search(s)  # must not raise
    assert ranked  # KB still returned
