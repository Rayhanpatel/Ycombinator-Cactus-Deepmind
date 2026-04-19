"""Tests for src.reddit_fetcher — duck-typed fakes, no network, no praw."""

from types import SimpleNamespace

import pytest

from src.reddit_fetcher import RedditFetcher


def _author(name: str, karma: int = 0, flair: str = None, created_utc: float = None):
    return SimpleNamespace(
        name=name,
        comment_karma=karma,
        author_flair_text=flair,
        created_utc=created_utc,
    )


def _comment(
    body: str,
    author=None,
    flair: str = None,
    score: int = 0,
    permalink: str = "/r/HVAC/comments/abc/_/x",
    replies=None,
    created_utc: float = 1_700_000_000.0,
):
    # Mirror real PRAW: flair lives on the comment, not the Redditor. If the
    # test didn't set one explicitly, fall back to the author's stored flair.
    author_flair = flair if flair is not None else getattr(author, "author_flair_text", None)
    return SimpleNamespace(
        body=body,
        author=author,
        author_flair_text=author_flair,
        score=score,
        permalink=permalink,
        replies=replies or [],
        created_utc=created_utc,
    )


class _FakeComments:
    """Mimics submission.comments with a replace_more() method."""
    def __init__(self, top_level):
        self._top = top_level

    def replace_more(self, limit=0):
        return None

    def __iter__(self):
        return iter(self._top)


def _submission(title, selftext, author, score, comments, permalink="/r/HVAC/comments/abc/"):
    return SimpleNamespace(
        title=title,
        selftext=selftext,
        author=author,
        score=score,
        author_flair_text=getattr(author, "author_flair_text", None),
        permalink=permalink,
        comments=_FakeComments(comments),
        created_utc=1_700_000_000.0,
    )


def _fresh_fetcher():
    """Build a fetcher without a real praw client."""
    f = RedditFetcher.__new__(RedditFetcher)
    f.allowed_subs = ("HVAC",)
    f.fetch_author_age = False
    f._reddit = None
    return f


def test_submission_mapping_fills_base_fields():
    fetcher = _fresh_fetcher()
    sub = _submission(
        title="X14 condensate overflow",
        selftext="Anyone seen this?",
        author=_author("asker", karma=5),
        score=42,
        comments=[],
    )
    doc = fetcher._submission_to_doc(sub)

    assert doc.url == "https://reddit.com/r/HVAC/comments/abc/"
    assert doc.title.startswith("X14")
    assert doc.depth == 0
    assert doc.self_upvotes == 42
    assert doc.author == "asker"
    assert doc.author_karma == 5


def test_comment_tree_walks_depth_and_parent_score():
    fetcher = _fresh_fetcher()
    pro = _author("veteran", karma=12000, flair="Certified HVAC-Pro")
    newbie = _author("newbie", karma=2)

    deep = _comment("Float sticks — swap the pump assembly.", author=pro, score=30,
                    permalink="/r/HVAC/comments/abc/_/deep")
    parent = _comment("What error code?", author=newbie, score=15, replies=[deep],
                      permalink="/r/HVAC/comments/abc/_/parent")
    sub = _submission(
        title="X14 condensate overflow",
        selftext="",
        author=newbie,
        score=120,
        comments=[parent],
    )

    docs = fetcher._submission_tree_to_docs(sub, depth_limit=6)
    by_author = {d.author: d for d in docs if d.author}

    # Submission + parent + deep = 3 docs
    assert len(docs) == 3
    # Depth-1 parent sees submission.score as parent_upvotes
    assert by_author["newbie"].depth in (0, 1)  # submission is newbie too
    parent_doc = next(d for d in docs if d.depth == 1)
    assert parent_doc.parent_upvotes == 120
    deep_doc = next(d for d in docs if d.depth == 2)
    assert deep_doc.parent_upvotes == 15
    assert deep_doc.author_flair == "Certified HVAC-Pro"


def test_depth_limit_truncates_deep_branches():
    fetcher = _fresh_fetcher()
    leaf = _comment("leaf", author=_author("a"), score=1)
    d3 = _comment("d3", author=_author("b"), score=1, replies=[leaf])
    d2 = _comment("d2", author=_author("c"), score=1, replies=[d3])
    d1 = _comment("d1", author=_author("d"), score=1, replies=[d2])
    sub = _submission("t", "", _author("op"), 10, [d1])

    docs = fetcher._submission_tree_to_docs(sub, depth_limit=2)
    depths = sorted(d.depth for d in docs)
    # submission (0), d1 (1), d2 (2) — d3 and leaf dropped
    assert depths == [0, 1, 2]


def test_sibling_affirmations_counted_among_reply_set():
    fetcher = _fresh_fetcher()
    # Three siblings under the same parent. Two affirm.
    sib_a = _comment("This is the fix, worked on mine.", author=_author("x"), score=4)
    sib_b = _comment("can confirm, saw this last week", author=_author("y"), score=3)
    sib_c = _comment("Try checking the thermistor resistance first.",
                     author=_author("pro", flair="HVAC Technician"), score=20,
                     permalink="/r/HVAC/comments/abc/_/c")
    parent = _comment("same symptom here — any ideas?", author=_author("op"),
                      score=5, replies=[sib_a, sib_b, sib_c])
    sub = _submission("t", "", _author("op"), 50, [parent])

    docs = fetcher._submission_tree_to_docs(sub, depth_limit=6)
    pro_doc = next(d for d in docs if d.author == "pro")
    # sib_c's siblings are sib_a and sib_b — both affirmations.
    assert pro_doc.sibling_affirmations == 2


def test_deleted_authors_handled_gracefully():
    fetcher = _fresh_fetcher()
    deleted = _comment("removed content", author=None, score=0)
    sub = _submission("t", "", None, 10, [deleted])

    docs = fetcher._submission_tree_to_docs(sub, depth_limit=6)
    assert all(d.author is None for d in docs)
    # Shouldn't crash when scoring the tree.


def test_fetch_author_age_opt_in():
    fetcher = _fresh_fetcher()
    fetcher.fetch_author_age = False
    a = _author("old", created_utc=1.0)
    assert fetcher._author_age_days(a) is None

    fetcher.fetch_author_age = True
    age = fetcher._author_age_days(a)
    assert age is not None and age > 10_000  # unix epoch = very old
