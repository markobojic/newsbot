from datetime import date, datetime
from itertools import zip_longest
from zoneinfo import ZoneInfo

import httpx2

from config import CAMPS, load_holdings, load_sources
from errors import ToolError, from_http_error, with_retries
from tools import chaos, fx, markets, rss, weather
from tools.parallel import fetch_all
from tools.text import normalize

# --- Tool 1: get_weather ------------------------------------------------------
# Coordinates live in code, not in the model's head: the model is not a reliable
# geocoder. The enum below is built from these keys, so the model can only send
# a city we can actually look up.
CITIES = {
    "Novi Sad": (45.2671, 19.8335),
    "Belgrade": (44.8125, 20.4612),
}

# A tool definition is ALL the model knows about a tool: name, description,
# input_schema. It never sees the Python code or its docstrings (2.1).
# A good description says: what it returns, when to use it, what it does NOT do,
# and what to do instead for unsupported input.
GET_WEATHER_TOOL = {
    "name": "get_weather",  # must match the key in HANDLERS (block.name arrives as this string)
    "description": (
        "Get the daily weather forecast for a city in Serbia, starting today "
        "(Europe/Belgrade time). Returns one entry per day with: date (YYYY-MM-DD), "
        "min_c and max_c (°C), precip_chance_pct (highest chance of rain or snow "
        "that day, 0-100), and snowfall_cm (expected snow; > 0 means snow is likely). "
        "Use it whenever the user asks about weather, temperature, rain or snow. "
        "It does NOT return past weather, hourly detail, wind or air quality, and "
        "only supports the cities listed in the `city` enum. For any other city, "
        "say it is not supported instead of picking the nearest one."
    ),
    # JSON Schema for the arguments. block.input arrives as a dict shaped like this.
    # The schema guides the model; it is not a hard guarantee (strict mode: Phase 6).
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "enum": list(CITIES),  # only these exact values are allowed
                "description": "City to forecast, e.g. \"Novi Sad\".",
            },
            "days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 7,  # small range = small tool result = less context (5.1)
                "description": "Number of days starting today. Use 1 for today only.",
            },
        },
        "required": ["city"],  # days is optional; its default lives in the adapter
    },
}


def run_get_weather(tool_input: dict) -> list[dict]:
    """Adapter: tool input (what the model sends) -> Python function call."""
    # The tool interface (city name) and the Python signature (lat/lon) are
    # deliberately different; this function is the bridge.
    city = tool_input.get("city")
    if city not in CITIES:
        # The enum guides the model but doesn't guarantee (strict mode: Phase 6).
        # A different input would work, so this is validation (2.2).
        raise ToolError(
            "validation", False,
            f"Unsupported city {city!r}. Supported: {list(CITIES)}. "
            "Tell the user it is not supported; do not pick the nearest city.",
            source="get_weather",
        )
    lat, lon = CITIES[city]

    def call():
        try:
            chaos.maybe_fail("open-meteo")  # no-op unless CHAOS is set
            return weather.get_forecast(lat, lon, days=tool_input.get("days", 1))
        except httpx2.HTTPError as exc:
            # Only HTTP failures are translated. Anything else is a bug in my code
            # and must reach the loop's safety net unclassified.
            raise from_http_error(exc, "open-meteo") from exc

    # Validation above runs once; only the network call is retried.
    return with_retries(call)


# --- Tool 2: fetch_feed -------------------------------------------------------
# Feed URLs come from config/sources.yaml, a list I control (DECISIONS.md): the
# model never invents a URL. Same pattern as CITIES.
OUTLETS = load_sources()
FEEDS = {key: outlet["url"] for key, outlet in OUTLETS.items()}

# The model only sees enum keys like "n1" or "novosti". Spell out each outlet's
# name and camp so it can pick by camp (2.1). What the camps mean goes in the
# system prompt (Phase 5).
OUTLET_LIST = ", ".join(f"{key} ({o['name']}, camp: {o['camp']})" for key, o in OUTLETS.items())

FETCH_FEED_TOOL = {
    "name": "fetch_feed",
    # "Call it once per outlet" -> one call per source, can run in parallel.
    # "does NOT search by topic, use search_news" -> the two tools overlap (both
    # return headlines), so each description points to the other (2.1).
    "description": (
        "Get the latest headlines from one news outlet's RSS feed, newest first. "
        "Returns a list of items, each with: title, link (the article URL, to cite "
        "as the source) and published (date string as the outlet gives it, or "
        "\"unknown\"). Use it when the user asks what is in the news, or for "
        "headlines from a specific outlet. Call it once per outlet. "
        "It does NOT search by topic or keyword (use search_news to find who covered "
        "a topic), and does NOT return the article "
        "text: only the headline and link. Only the outlets in the `source` enum "
        "are available; for any other outlet, say it is not supported."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": list(FEEDS),
                "description": f"Outlet to read, e.g. \"bbc\". Outlets: {OUTLET_LIST}.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "How many of the newest items to return. Default 5.",
            },
        },
        "required": ["source"],
    },
}

def read_feed(source: str, limit: int | None) -> list[dict]:
    """Read one configured feed: chaos -> fetch -> classify -> retry. Raises ToolError.

    Shared by fetch_feed (one outlet) and search_news (many outlets), so both
    classify and retry failures the same way. limit=None returns every item.
    """

    def call():
        try:
            chaos.maybe_fail(source)  # no-op unless CHAOS is set
            return rss.fetch_feed(FEEDS[source], limit=limit)
        except httpx2.HTTPError as exc:
            # The adapter is the only layer that knows this URL is "n1": rss.py only
            # sees a URL, the loop doesn't know HTTP. So the translation lives here.
            raise from_http_error(exc, source) from exc
        except rss.FeedParseError as exc:
            # 200 OK but not a feed (e.g. an HTML page): the URL in config is wrong.
            # Waiting won't fix it and the model can't; only I can (see errors.py).
            raise ToolError(
                "permission", False,
                f"{source} returned something that is not a readable feed; the config "
                "probably needs updating. Do not retry. Report it as a coverage gap.",
                source,
            ) from exc

    return with_retries(call)


def run_fetch_feed(tool_input: dict) -> list[dict]:
    """Adapter: tool input (what the model sends) -> Python function call."""
    source = tool_input.get("source")
    if source not in FEEDS:
        raise ToolError(
            "validation", False,
            f"Unknown outlet {source!r}. Use one of the `source` enum values. "
            "If the user asked for an outlet that is not listed, say it is not supported.",
            source=str(source),
        )
    return read_feed(source, limit=tool_input.get("limit", 5))


# --- Tool 3: search_news ------------------------------------------------------
# Deliberately close to fetch_feed: both return headlines. The difference is WHO
# filters: here my code reads every feed and keeps only matches, so 500 headlines
# never enter the context (5.1). Its job in the brief: compare camps on the SAME
# event ("Contested: ..."), which fetch_feed can't do in one call.
MAX_SEARCH_RESULTS = 30  # keeps the tool result small; "truncated" tells the model

SEARCH_NEWS_TOOL = {
    "name": "search_news",
    "description": (
        "Find which outlets covered a topic: searches the headlines of all configured "
        "outlets (or one camp) for a keyword and returns only the matching headlines. "
        "Use it to compare how different camps reported the same event or person, "
        "e.g. after fetch_feed showed a topic. To see what one outlet has today "
        "regardless of topic, use fetch_feed instead. "
        "Searches headlines only (not article text) in each feed's latest items "
        "(roughly the last 1-2 days). Matching ignores case, Cyrillic vs Latin script "
        "and diacritics, so \"budzet\" also finds \"буџет\". "
        "Returns: results (each with source, camp, title, link to cite, published), "
        "searched (outlets that were read successfully), failed_sources (outlets that "
        "could not be read, with the reason) and truncated (true if more than "
        f"{MAX_SEARCH_RESULTS} matches; then use a more specific query). "
        "How to read it: an outlet in `searched` with no results did NOT cover the "
        "topic. An outlet in `failed_sources` is UNKNOWN: never say it ignored the "
        "topic, report it as a coverage gap instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 2,
                "description": (
                    "One short keyword or name as it would appear in a headline, "
                    "e.g. \"Vukićević\" or \"budžet\". Not a sentence: matching is "
                    "plain substring matching, so a long phrase finds almost nothing."
                ),
            },
            "camp": {
                "type": "string",
                "enum": sorted(CAMPS),
                "description": "Only search outlets in this camp. Omit to search all outlets.",
            },
        },
        "required": ["query"],
    },
}


def run_search_news(tool_input: dict) -> dict:
    """Adapter: search every (or one camp's) feed; partial results + named gaps (5.3)."""
    query = (tool_input.get("query") or "").strip()
    camp = tool_input.get("camp")
    if len(query) < 2:
        raise ToolError(
            "validation", False,
            "query must be a keyword of at least 2 characters, e.g. \"budžet\".",
            source="search_news",
        )
    if camp is not None and camp not in CAMPS:
        raise ToolError(
            "validation", False,
            f"Unknown camp {camp!r}. Use one of {sorted(CAMPS)}, or omit camp.",
            source="search_news",
        )

    sources = [key for key, o in OUTLETS.items() if camp is None or o["camp"] == camp]
    feeds, failures = fetch_all(sources, lambda source: read_feed(source, limit=None))

    if not feeds:
        # Nothing was readable: partial results are impossible, so this IS an error.
        # Each feed already had its own retries, so retrying the search is pointless.
        all_transient = all(err.category == "transient" for err in failures.values())
        raise ToolError(
            "transient" if all_transient else "permission", False,
            f"None of the {len(sources)} outlets could be read "
            f"({', '.join(failures)}). Do not retry. Report it as a coverage gap.",
            source="search_news",
        )

    needle = normalize(query)
    per_source = [
        [
            {
                "source": source,
                "camp": OUTLETS[source]["camp"],
                "title": item["title"],  # original text (Cyrillic stays Cyrillic): it gets cited
                "link": item["link"],
                "published": item["published"],
            }
            for item in items
            if needle in normalize(item["title"])
        ]
        for source, items in feeds.items()
    ]
    # Round-robin: 1st match of every outlet, then 2nd of every outlet, ... Without
    # this, the cap keeps only the outlets listed first (the SNS camp), and the camp
    # that publishes more crowds out the others: the bias this bot exists to avoid.
    matches = [m for row in zip_longest(*per_source) for m in row if m is not None]
    return {
        "results": matches[:MAX_SEARCH_RESULTS],
        # Only what was really read: "searched + no results" = didn't cover it.
        "searched": list(feeds),
        # Not read = unknown. The full error so the model can name the gap and why.
        "failed_sources": [err.to_dict() for err in failures.values()],
        "truncated": len(matches) > MAX_SEARCH_RESULTS,
    }

# --- Tool 4: get_holdings_quotes ----------------------------------------------
# No parameters on purpose: which stocks I hold is MY decision (config/holdings.yaml),
# so the model can't invent, forget or misspell a ticker. With nothing to choose,
# the name and description are its only guide for when to call it (2.1).
GET_HOLDINGS_QUOTES_TOOL = {
    "name": "get_holdings_quotes",
    "description": (
        "Get the last closing price and daily change for each of the user's stock "
        "holdings (the fixed list in the user's config; it takes no input). Use it "
        "whenever the user asks about their stocks, holdings, portfolio or markets. "
        "Returns quotes, each with: ticker, name (company name, as used in headlines), "
        "price, currency, change_pct (last close vs the close before it, in %), "
        "notable (true if the absolute move is above notable_move_pct) and as_of "
        "(date of that close, YYYY-MM-DD). Also returns failed (holdings that could "
        "not be read, with the reason) and notable_move_pct. "
        "Prices are the LAST CLOSE, not live: say \"closed at\" with the as_of date, "
        "never \"is trading at\". Use `notable` as given; do not apply your own "
        "threshold. For a notable move, look for a reason with search_news using the "
        "company name; if none is found, say no reason was found instead of guessing. "
        "Report every holding in `failed` as unavailable; never leave it out silently. "
        "Source to cite: Yahoo Finance. It does NOT return stocks the user does not "
        "hold, intraday prices or price history; for any other stock, say it is not "
        "supported."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

# Read once at import, like OUTLETS: a broken holdings.yaml crashes at startup.
HOLDINGS = load_holdings()


def read_quote(ticker: str) -> dict:
    """One ticker: chaos -> fetch -> classify -> retry. Raises ToolError (same pattern as read_feed)."""

    def call():
        try:
            chaos.maybe_fail(ticker)  # no-op unless CHAOS is set
            return markets.get_quote(ticker)
        except httpx2.HTTPError as exc:
            # 429 is common on this unofficial endpoint: transient, retried.
            # 404 = Yahoo doesn't know the symbol: my config is wrong (permission).
            raise from_http_error(exc, ticker) from exc
        except markets.MarketDataError as exc:
            # Yahoo answered, but has fewer than 2 prices (e.g. newly listed). Not
            # temporary within seconds, not the model's input, not my config: a
            # valid "no" from the domain, so business. Accept it and report it.
            raise ToolError(
                "business", False,
                f"{ticker}: not enough trading data to compute a daily change. "
                "Do not retry. Report it as unavailable today.",
                ticker,
            ) from exc

    return with_retries(call)


def run_get_holdings_quotes(tool_input: dict) -> dict:
    """Adapter: quotes for every holding in config; partial results + named gaps (5.3)."""
    # tool_input is always {}: the tool takes no input (see the comment above the tool).
    threshold = HOLDINGS["notable_move_pct"]
    names = {h["ticker"]: h["name"] for h in HOLDINGS["holdings"]}
    quotes, failures = fetch_all(list(names), read_quote)

    if not quotes:
        # Nothing to return. Each ticker already had its own retries.
        raise ToolError(
            "transient" if all(e.category == "transient" for e in failures.values()) else "permission",
            False,
            f"None of the holdings could be read ({', '.join(failures)}). "
            "Do not retry. Report the markets section as unavailable.",
            source="get_holdings_quotes",
        )

    return {
        "quotes": [
            {
                **quote,
                "name": names[ticker],  # how headlines name it, for search_news
                # Decided in code, not by the model: a fixed rule should give the same
                # answer every time (4.1). abs(): -3% matters as much as +3%.
                "notable": abs(quote["change_pct"]) > threshold,
            }
            for ticker, quote in quotes.items()
        ],
        "failed": [err.to_dict() for err in failures.values()],
        # So the model can say WHY a move counts as notable ("moved more than 1.5%").
        "notable_move_pct": threshold,
    }

# --- Tool 5: get_rsd_rate -----------------------------------------------------
# No parameters: the brief always shows EUR -> RSD (DECISIONS.md). NBS publishes
# on working days only, so on a weekend or holiday the latest list is older than
# today. That is correct, not an error; only a list too old for that is an error.
MAX_LIST_AGE_DAYS = 7  # longest holiday break (Orthodox Easter) is 4-5 days

GET_RSD_RATE_TOOL = {
    "name": "get_rsd_rate",
    "description": (
        "Get the official National Bank of Serbia (NBS) middle exchange rate for the "
        "euro: how many Serbian dinars (RSD) one euro (EUR) is worth, from the latest "
        "NBS exchange rate list (it takes no input). Use it whenever the user asks "
        "about the euro, the dinar or the exchange rate, and for the markets section "
        "of the brief. Returns rate (RSD for 1 EUR), list_date (YYYY-MM-DD, the day "
        "NBS published that list) and list_number. "
        "NBS publishes only on working days, so on weekends and holidays list_date is "
        "the last working day: that rate is still the official one, not an error. "
        "Cite it with the list date, e.g. \"EUR = 117.64 RSD (NBS, list of 20 Nov)\", "
        "never with today's date. "
        "It does NOT return other currencies, past rates, or the buying/selling rates "
        "banks use; for those, say they are not supported."
    ),
    "input_schema": {"type": "object", "properties": {}},
}


def today_in_belgrade() -> date:
    """Today's date where NBS (and the reader) are; a function so tests can replace it."""
    return datetime.now(ZoneInfo("Europe/Belgrade")).date()


def run_get_rsd_rate(tool_input: dict) -> dict:
    """Adapter: the latest NBS list for today. One source, one value: no partial results."""
    today = today_in_belgrade()

    def call():
        try:
            chaos.maybe_fail("nbs")  # no-op unless CHAOS is set
            return fx.get_eur_rsd(today)
        except httpx2.HTTPError as exc:
            raise from_http_error(exc, "nbs") from exc
        except fx.FxParseError as exc:
            # NBS answered but the page changed: only I can fix the scraper.
            raise ToolError(
                "permission", False,
                "NBS page layout changed; the EUR rate could not be read. Do not retry. "
                "Report EUR -> RSD as unavailable.",
                "nbs",
            ) from exc

    result = with_retries(call)
    age_days = (today - date.fromisoformat(result["list_date"])).days
    if age_days > MAX_LIST_AGE_DAYS:
        # Too old for a weekend or holiday: the page stopped updating or the parser
        # read the wrong list. A human has to look. Not returned at all, so an old
        # rate can't end up in the brief looking like today's.
        raise ToolError(
            "permission", False,
            f"Latest NBS list is from {result['list_date']}, {age_days} days old. "
            "Do not use it. Report EUR -> RSD as unavailable.",
            "nbs",
        )
    return result


# What we send to the API on every call (tool definitions count as input tokens).
TOOLS = [
    GET_WEATHER_TOOL,
    FETCH_FEED_TOOL,
    SEARCH_NEWS_TOOL,
    GET_HOLDINGS_QUOTES_TOOL,
    GET_RSD_RATE_TOOL,
]
# Tool name (what the model asks for) -> adapter (what we run).
# Values are functions, not calls (no parentheses). Keys come from the tool dicts
# so a rename can't break the lookup.
HANDLERS = {
    GET_WEATHER_TOOL["name"]: run_get_weather,
    FETCH_FEED_TOOL["name"]: run_fetch_feed,
    SEARCH_NEWS_TOOL["name"]: run_search_news,
    GET_HOLDINGS_QUOTES_TOOL["name"]: run_get_holdings_quotes,
    GET_RSD_RATE_TOOL["name"]: run_get_rsd_rate,
}