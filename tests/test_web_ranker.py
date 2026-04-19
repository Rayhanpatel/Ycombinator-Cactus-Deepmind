"""Tests for src.web_ranker — no network, no model download."""

import time
from pathlib import Path

import pytest

from src.web_ranker import (
    WebDoc,
    WebRanker,
    _agreement,
    _depth_bonus,
    _domain_of,
    _expertise,
    count_affirmations,
)


def _fake_vec(bits: list[float]) -> list[float]:
    """Build a tiny deterministic vector for cosine math."""
    return bits


@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    return tmp_path / "ranker_state.json"


def test_domain_of_strips_www_and_lowercases():
    assert _domain_of("https://WWW.Carrier.com/support/page") == "carrier.com"
    assert _domain_of("https://support.movincool.com/x") == "support.movincool.com"
    assert _domain_of("not a url") == ""


def test_authority_wins_tie_when_cosine_zero(tmp_state):
    """With no KB and no query vec, authority + UCB should order results."""
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    docs = [
        WebDoc(url="https://randomblog.example/post", text="cooling"),
        WebDoc(url="https://support.movincool.com/x14", text="cooling"),
    ]
    ranked = ranker.rank("condensate pump", docs)
    # Manufacturer support should land on top.
    assert ranked[0].doc.url.startswith("https://support.movincool.com")
    assert ranked[0].components["authority"] == 1.0
    assert ranked[1].components["authority"] == 0.0


def test_ucb_bonus_favors_unseen_domains(tmp_state):
    """A domain we've visited a lot gets a smaller explore bonus."""
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    for _ in range(50):
        ranker.record_visit("https://support.movincool.com/x14")

    docs = [
        WebDoc(url="https://support.movincool.com/x14", text="a"),
        WebDoc(url="https://newsource.example/page", text="a"),
    ]
    ranked = ranker.rank("q", docs)
    by_domain = {r.components["domain"]: r for r in ranked}
    assert by_domain["newsource.example"].components["ucb_bonus"] > \
           by_domain["support.movincool.com"].components["ucb_bonus"]


def test_freshness_decays_with_age(tmp_state):
    ranker = WebRanker(kb_engine=None, state_file=tmp_state, half_life_days=30)
    now = time.time()
    fresh = WebDoc(url="https://x.example/a", text="x", last_modified=now)
    old = WebDoc(url="https://x.example/b", text="x", last_modified=now - 365 * 86400)
    ranked = {r.doc.url: r for r in ranker.rank("q", [fresh, old])}
    assert ranked["https://x.example/a"].components["freshness"] > \
           ranked["https://x.example/b"].components["freshness"]
    # ~12 half-lives → effectively zero
    assert ranked["https://x.example/b"].components["freshness"] < 0.01


def test_unknown_lastmodified_is_neutral(tmp_state):
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    doc = WebDoc(url="https://x.example/a", text="x", last_modified=None)
    ranked = ranker.rank("q", [doc])
    assert ranked[0].components["freshness"] == 0.5


def test_state_persists_across_instances(tmp_state):
    a = WebRanker(kb_engine=None, state_file=tmp_state)
    a.record_visit("https://example.com/one")
    a.record_visit("https://example.com/two")

    b = WebRanker(kb_engine=None, state_file=tmp_state)
    assert b._source_counts["example.com"] == 2


def test_rank_returns_empty_for_empty_input(tmp_state):
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    assert ranker.rank("q", []) == []


def test_top_k_limits_results(tmp_state):
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    docs = [WebDoc(url=f"https://d{i}.example/", text="x") for i in range(5)]
    assert len(ranker.rank("q", docs, top_k=2)) == 2


def test_redundancy_penalty_with_stubbed_kb(tmp_state, monkeypatch):
    """A doc whose vector matches a KB entry perfectly should be demoted."""

    class StubKB:
        entries = [{"embedding": [1.0, 0.0, 0.0]}]

        def _get_embed_model(self):
            return None  # no real model — we'll supply vectors manually

    ranker = WebRanker(kb_engine=StubKB(), state_file=tmp_state)
    # Short-circuit the query embedding so w_sim contributes equally.
    monkeypatch.setattr(ranker, "_embed", lambda text: [0.0, 1.0, 0.0])

    dup_doc = WebDoc(url="https://a.example/", text="t", embedding=[1.0, 0.0, 0.0])
    fresh_doc = WebDoc(url="https://b.example/", text="t", embedding=[0.0, 1.0, 0.0])

    ranked = {r.doc.url: r for r in ranker.rank("q", [dup_doc, fresh_doc])}
    assert ranked["https://a.example/"].components["redundancy"] == pytest.approx(1.0)
    assert ranked["https://b.example/"].components["redundancy"] == pytest.approx(0.0)
    assert ranked["https://b.example/"].score > ranked["https://a.example/"].score


def test_expertise_verified_flair_dominates():
    doc = WebDoc(
        url="https://reddit.com/r/HVAC/comments/x/y",
        text="...",
        author="techguy",
        author_flair="Certified HVAC-Pro — 15yr commercial",
    )
    assert _expertise(doc) == 1.0


def test_expertise_pro_indicator_mid_tier():
    doc = WebDoc(
        url="https://reddit.com/r/HVAC/comments/x/y",
        text="...",
        author="bob",
        author_flair="Residential HVAC",
    )
    assert _expertise(doc) == pytest.approx(0.7, abs=0.01)


def test_expertise_unknown_author_scores_zero():
    assert _expertise(WebDoc(url="https://x/", text="...")) == 0.0


def test_expertise_karma_and_age_stack():
    doc = WebDoc(
        url="https://x/",
        text="...",
        author="veteran",
        author_karma=50_000,
        author_account_age_days=1500,
    )
    # Karma ~ log10(50001)/10 ≈ 0.47 → capped to 0.4, plus 0.1 age → 0.5
    assert 0.45 <= _expertise(doc) <= 0.55


def test_depth_bonus_needs_parent_engagement():
    """A depth-5 reply on a 0-upvote thread is still noise."""
    doc = WebDoc(url="https://x/", text="...", depth=5, parent_upvotes=0)
    assert _depth_bonus(doc) == 0.0


def test_depth_bonus_rewards_deep_engaged_replies():
    shallow = WebDoc(url="https://x/a", text="...", depth=1, parent_upvotes=100)
    deep = WebDoc(url="https://x/b", text="...", depth=4, parent_upvotes=100)
    assert _depth_bonus(deep) > _depth_bonus(shallow) > 0.0


def test_agreement_saturates():
    assert _agreement(WebDoc(url="https://x/", text="...", sibling_affirmations=0)) == 0.0
    one = _agreement(WebDoc(url="https://x/", text="...", sibling_affirmations=1))
    many = _agreement(WebDoc(url="https://x/", text="...", sibling_affirmations=50))
    assert 0.0 < one < many <= 1.0


def test_count_affirmations_matches_phrases():
    siblings = [
        "This is the fix, had the exact same symptom on my X14",
        "completely unrelated comment about the weather",
        "Can confirm — solved it for me too",
        "eh, I don't know",
    ]
    assert count_affirmations(siblings) == 2


def test_cracked_technician_outranks_manual_page(tmp_state):
    """
    The whole point of the forum extension: a deeply-nested pro comment
    with sibling affirmations should beat a generic top-level page when
    the cosine score is comparable.
    """
    ranker = WebRanker(kb_engine=None, state_file=tmp_state)
    manual_page = WebDoc(
        url="https://support.movincool.com/generic-faq",
        text="General troubleshooting guidance.",
    )
    pro_reply = WebDoc(
        url="https://reddit.com/r/HVAC/comments/abc/def",
        text="On the X14 specifically the condensate pump float sticks when...",
        author="hvacveteran",
        author_flair="Certified HVAC-Pro",
        author_karma=12000,
        author_account_age_days=2200,
        depth=3,
        parent_upvotes=120,
        sibling_affirmations=4,
    )
    ranked = ranker.rank("X14 condensate overflow", [manual_page, pro_reply])
    assert ranked[0].doc.url.startswith("https://reddit.com")
    assert ranked[0].components["expertise"] == 1.0
    assert ranked[0].components["depth_bonus"] > 0
    assert ranked[0].components["agreement"] > 0


def test_kb_references_seed_authority(tmp_state):
    class StubKB:
        entries = [
            {"references": [{"url": "https://newvendor.example/manual"}]},
            {"references": ["https://anothervendor.example/"]},
        ]

        def _get_embed_model(self):
            return None

    ranker = WebRanker(kb_engine=StubKB(), state_file=tmp_state)
    assert ranker.authority["newvendor.example"] == 0.9
    assert ranker.authority["anothervendor.example"] == 0.9
