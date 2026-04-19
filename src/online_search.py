"""
Online HVAC forum search — explicit escalation tool.

This is the ONE part of HVAC Copilot that leaves the device. It is never
chained automatically; the model calls it only when the curated KB has no
answer or the user explicitly asks to look online. Every call shows up in
the tool-activity panel with a 🌐 badge.

Primary path  : Amogh's PRAW-based RedditFetcher (rich comment-tree data
                when REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET are set).
Fallback path : anonymous HTTPS to reddit.com/.../search.json using the
                already-present `requests` lib. Works without credentials.

A 5-second wall-clock cap on either path keeps the demo responsive.
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import asdict, is_dataclass
from typing import Any

import requests

from src.config import cfg

logger = logging.getLogger("hvac.online")

# Curated subs — adopted from Amogh's src/reddit_fetcher.py::DEFAULT_SUBS.
# Technicians actually post here; broader subs dilute the signal.
SUBS = ("HVAC", "hvacadvice", "Refrigeration")

TIMEOUT_S = 5.0
MAX_RESULTS = 5
TEXT_TRIM = 320   # chars per result body
TITLE_TRIM = 180

_HTTP_HEADERS = {
    "User-Agent": "cactus-hvac-copilot/0.1 (hackathon demo, read-only)",
}


def _praw_available() -> bool:
    if not cfg.REDDIT_CLIENT_ID or not cfg.REDDIT_CLIENT_SECRET:
        return False
    try:
        import praw  # noqa: F401
        return True
    except ImportError:
        return False


def _doc_to_dict(doc: Any) -> dict:
    """Convert Amogh's WebDoc dataclass (or anything dict-like) to a flat dict."""
    if is_dataclass(doc):
        d = asdict(doc)
    elif isinstance(doc, dict):
        d = doc
    else:
        d = {"url": getattr(doc, "url", ""), "title": getattr(doc, "title", ""),
             "text": getattr(doc, "text", "")}
    return {
        "title": (d.get("title") or "")[:TITLE_TRIM],
        "text": (d.get("text") or "")[:TEXT_TRIM],
        "url": d.get("url", ""),
        "score": d.get("self_upvotes") or d.get("score") or 0,
        "depth": d.get("depth", 0),
    }


def _search_praw(query: str) -> dict:
    """Use Amogh's RedditFetcher. Shallow depth for speed."""
    from src.reddit_fetcher import RedditFetcher
    fetcher = RedditFetcher(allowed_subs=SUBS)
    if not fetcher.is_available:
        return {"ok": False, "reason": "praw-unavailable"}
    docs = fetcher.search(query, limit=3, comment_depth_limit=1)
    # Prefer the top-level submissions (depth=0) — cleaner summaries.
    subs = [d for d in docs if getattr(d, "depth", 0) == 0][:MAX_RESULTS]
    results = [_doc_to_dict(d) for d in subs]
    return {
        "ok": True,
        "source": "reddit via praw",
        "subs_queried": list(SUBS),
        "results": results,
    }


def _search_json(query: str) -> dict:
    """Anonymous fallback. Hits reddit.com JSON endpoint on each sub."""
    results: list[dict] = []
    errors: list[str] = []
    for sub in SUBS:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/search.json",
                params={
                    "q": query,
                    "restrict_sr": "on",
                    "limit": 3,
                    "sort": "relevance",
                    "t": "year",
                },
                headers=_HTTP_HEADERS,
                timeout=3.0,
            )
            r.raise_for_status()
            children = (r.json().get("data") or {}).get("children") or []
            for c in children:
                d = c.get("data") or {}
                results.append(_doc_to_dict({
                    "title": d.get("title", ""),
                    "text": d.get("selftext") or "",
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "score": d.get("score", 0),
                }))
        except Exception as e:
            errors.append(f"r/{sub}: {type(e).__name__}")
            continue
    # Sort by score across all subs, trim to top N.
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:MAX_RESULTS]
    if not results and errors:
        return {"ok": False, "reason": "; ".join(errors)[:200]}
    return {
        "ok": True,
        "source": "reddit via json",
        "subs_queried": list(SUBS),
        "results": results,
    }


def search(query: str) -> dict:
    """
    Public entry point. Wraps either path in a hard wall-clock timeout so
    a stuck HTTP call can't hang the model's tool loop.
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "reason": "empty query"}

    use_praw = _praw_available()
    worker = _search_praw if use_praw else _search_json
    logger.info("🌐 online search (%s): %s", "praw" if use_praw else "json", q[:80])

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(worker, q)
            return fut.result(timeout=TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        return {"ok": False, "reason": "timeout"}
    except Exception as e:
        logger.warning("online search failed: %s", e)
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:120]}"}
