"""Phase 0: summarize 5 headlines from one RSS feed with one Messages API call."""

import anthropic
import feedparser
import httpx2
from dotenv import load_dotenv

FEED_URL = "https://feeds.bbci.co.uk/news/world/rss.xml"
MODEL = "claude-haiku-5-5"
N_ITEMS = 5

SYSTEM_PROMPT = """You write a short news summary for one reader in Serbia who reads it \
in the morning to know what happened in the world overnight.

Rules:
- Use only the headlines the user gives you. Do not add facts, numbers, names or \
background from your own knowledge.
- End every bullet with the source link of the headline it is based on, in parentheses.
- Never invent or shorten a link; copy it exactly as given.
- If two headlines are about the same event, merge them into one bullet and give both links.

If a headline is too vague to say what happened, do not guess. Repeat it as given \
and mark it "(unclear from headline)".

Format: 3-5 bullets, one sentence each, plain text, in English. No introduction \
and no closing remarks."""


def read_feed(url: str, n: int) -> list[dict]:
    """Return the first n items of an RSS feed as {title, link, published}."""
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
        for e in feed.entries[:n]
    ]


def format_items(items: list[dict]) -> str:
    """Render items as a numbered list the model can cite by link."""
    return "\n".join(
        f"{i}. {it['title']}\n   {it['link']}\n   published: {it['published']}"
        for i, it in enumerate(items, 1)
    )


def main() -> None:
    load_dotenv()  # puts ANTHROPIC_API_KEY into the environment
    items = read_feed(FEED_URL, N_ITEMS)
    headlines = format_items(items)
    print(headlines, "\n" + "-" * 60)

    # --- Your part: the Messages API call --------------------------------
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    # TODO 2: done - SYSTEM_PROMPT at the top of the file.
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,  # includes thinking tokens, not just the visible text
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Today's headlines:\n\n{headlines}"},
        ],
    )
    for block in response.content:
        if block.type == "text":
            print(block.text)
    usage = response.usage
    print("-" * 60)
    print(f"stop_reason: {response.stop_reason}")
    print(
        f"tokens: input={usage.input_tokens} output={usage.output_tokens} "
        f"(thinking={usage.output_tokens_details.thinking_tokens})"
    )


if __name__ == "__main__":
    main()
