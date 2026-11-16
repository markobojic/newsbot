"""Read an RSS feed into small, JSON-serializable dicts. Plain Python, no Claude."""

import feedparser
import httpx2


def fetch_feed(url: str, limit: int = 5) -> list[dict]:
    """Return the first `limit` items of an RSS feed as {title, link, published}."""
    # Download with httpx2 (system trust store), not feedparser's urllib,
    # which fails on macOS python.org builds with CERTIFICATE_VERIFY_FAILED.
    resp = httpx2.get(url, timeout=10, follow_redirects=True)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Could not read feed {url}: {feed.bozo_exception}")
    return [
        {
            "title": e.get("title", "").strip(),
            "link": e.get("link", ""),
            "published": e.get("published", "unknown"),
        }
        for e in feed.entries[:limit]
    ]
