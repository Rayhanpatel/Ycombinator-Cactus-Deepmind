"""
Reddit Fetcher — read-only PRAW wrapper that maps submissions + comment
trees into `WebDoc` objects ready for `WebRanker.rank()`.

No writes, ever — `read_only=True` is hard-coded. Requires a Reddit
"script" app (reddit.com/prefs/apps) with client_id + client_secret.

Usage:
    from src.reddit_fetcher import RedditFetcher
    from src.web_ranker import WebRanker
    from src.kb_engine import KBEngine

    kb = KBEngine(); kb.load()
    fetcher = RedditFetcher()
    docs = fetcher.search("MovinCool X14 condensate overflow", limit=5)
    ranked = WebRanker(kb).rank("MovinCool X14 condensate overflow", docs)

PRAW handles rate limiting automatically. The fetcher is intentionally
thin — all ranking logic lives in `web_ranker.py`.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable, Optional

from src.config import cfg
from src.web_ranker import AFFIRMATION_PHRASES, WebDoc, count_affirmations

logger = logging.getLogger(__name__)

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logger.info("praw not installed. Reddit fetcher disabled. Run: pip install praw")


# Subs where technicians actually hang out. Keep tight — broader subs
# dilute expertise signal. Edit as you learn the community.
DEFAULT_SUBS: tuple[str, ...] = (
    "HVAC",
    "hvacadvice",
    "Refrigeration",
    "askanelectrician",
    "AskElectricians",
)


class RedditFetcher:
    """Thin read-only PRAW wrapper → list[WebDoc]."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        allowed_subs: Iterable[str] = DEFAULT_SUBS,
        fetch_author_age: bool = False,
    ):
        self.allowed_subs = tuple(allowed_subs)
        self.fetch_author_age = fetch_author_age
        self._reddit = None

        cid = client_id or cfg.REDDIT_CLIENT_ID
        csec = client_secret or cfg.REDDIT_CLIENT_SECRET
        ua = user_agent or cfg.REDDIT_USER_AGENT

        if PRAW_AVAILABLE and cid and csec:
            self._reddit = praw.Reddit(
                client_id=cid,
                client_secret=csec,
                user_agent=ua,
            )
            self._reddit.read_only = True  # belt and suspenders
            logger.info(
                f"🤖 Reddit fetcher ready (read-only, subs={list(self.allowed_subs)})"
            )
        else:
            logger.warning(
                "🤖 Reddit fetcher not available (missing praw or credentials)"
            )

    @property
    def is_available(self) -> bool:
        return self._reddit is not None

    # ── public API ───────────────────────────────────────────────
    def search(
        self,
        query: str,
        limit: int = 10,
        subreddits: Optional[Iterable[str]] = None,
        comment_depth_limit: int = 6,
    ) -> list[WebDoc]:
        """
        Search allowed subs for `query`, flatten every comment tree, and
        return WebDocs with forum fields filled in. Stays within PRAW's
        built-in rate limits — no sleep needed.
        """
        if not self.is_available:
            logger.error("Reddit fetcher not available.")
            return []

        subs = tuple(subreddits) if subreddits else self.allowed_subs
        docs: list[WebDoc] = []

        for sub_name in subs:
            try:
                subreddit = self._reddit.subreddit(sub_name)
                for submission in subreddit.search(query, limit=limit):
                    docs.extend(self._submission_tree_to_docs(
                        submission, comment_depth_limit
                    ))
            except Exception as e:
                logger.warning(f"reddit: search failed in r/{sub_name}: {e}")
                continue

        logger.info(f"🤖 Reddit: fetched {len(docs)} docs across {len(subs)} subs")
        return docs

    # ── internal mapping ─────────────────────────────────────────
    def _submission_tree_to_docs(
        self, submission, depth_limit: int
    ) -> list[WebDoc]:
        """Flatten one submission + its comments into WebDocs."""
        docs = [self._submission_to_doc(submission)]

        # Drop "load more" placeholders so comment iteration is flat.
        try:
            submission.comments.replace_more(limit=0)
        except Exception as e:
            logger.debug(f"reddit: replace_more failed ({e}); continuing")
            return docs

        submission_url = f"https://reddit.com{submission.permalink}"
        submission_score = getattr(submission, "score", 0) or 0
        # Walk the tree: for each comment we need (depth, parent_score, sibling_texts).
        stack: list[tuple[object, int, int, list[str]]] = []
        top_level = list(submission.comments)
        top_level_texts = [self._comment_body(c) for c in top_level]
        for c in top_level:
            stack.append((c, 1, submission_score, top_level_texts))

        while stack:
            comment, depth, parent_score, sibling_texts = stack.pop()
            if depth > depth_limit:
                continue
            docs.append(self._comment_to_doc(
                comment, submission_url, depth, parent_score, sibling_texts
            ))
            replies = list(getattr(comment, "replies", []) or [])
            if not replies:
                continue
            reply_texts = [self._comment_body(r) for r in replies]
            own_score = getattr(comment, "score", 0) or 0
            for r in replies:
                stack.append((r, depth + 1, own_score, reply_texts))

        return docs

    def _submission_to_doc(self, submission) -> WebDoc:
        author = getattr(submission.author, "name", None) if submission.author else None
        return WebDoc(
            url=f"https://reddit.com{submission.permalink}",
            title=getattr(submission, "title", "") or "",
            text=getattr(submission, "selftext", "") or "",
            last_modified=_safe_utc(submission, "created_utc"),
            author=author,
            author_flair=getattr(submission, "author_flair_text", None),
            author_karma=self._author_topical_karma(submission.author),
            author_account_age_days=self._author_age_days(submission.author),
            depth=0,
            parent_upvotes=None,
            self_upvotes=getattr(submission, "score", None),
            sibling_affirmations=0,
        )

    def _comment_to_doc(
        self,
        comment,
        submission_url: str,
        depth: int,
        parent_upvotes: int,
        sibling_texts: list[str],
    ) -> WebDoc:
        author = getattr(comment.author, "name", None) if comment.author else None
        body = self._comment_body(comment)
        # Exclude this comment's own body from "sibling" texts.
        siblings = [t for t in sibling_texts if t != body]
        return WebDoc(
            url=f"https://reddit.com{getattr(comment, 'permalink', '')}",
            title="",
            text=body,
            last_modified=_safe_utc(comment, "created_utc"),
            author=author,
            author_flair=getattr(comment, "author_flair_text", None),
            author_karma=self._author_topical_karma(comment.author),
            author_account_age_days=self._author_age_days(comment.author),
            depth=depth,
            parent_upvotes=parent_upvotes,
            self_upvotes=getattr(comment, "score", None),
            sibling_affirmations=count_affirmations(siblings),
        )

    # ── author helpers ───────────────────────────────────────────
    def _comment_body(self, comment) -> str:
        return getattr(comment, "body", "") or ""

    def _author_topical_karma(self, author) -> Optional[int]:
        """
        Global karma only — PRAW doesn't expose per-sub karma without a
        separate listing call. This is a pragmatic first pass; upgrade to
        per-sub karma later by scanning `author.comments.new(limit=100)`
        and summing scores from `allowed_subs`.
        """
        if author is None:
            return None
        try:
            return int(getattr(author, "comment_karma", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            return None

    def _author_age_days(self, author) -> Optional[float]:
        """Extra API call per author — opt-in via fetch_author_age=True."""
        if author is None or not self.fetch_author_age:
            return None
        try:
            created = getattr(author, "created_utc", None)
            if created is None:
                return None
            return max(0.0, (time.time() - float(created)) / 86400.0)
        except (AttributeError, TypeError, ValueError):
            return None


def _safe_utc(obj, attr: str) -> Optional[float]:
    val = getattr(obj, attr, None)
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


__all__ = ["RedditFetcher", "DEFAULT_SUBS", "AFFIRMATION_PHRASES"]
