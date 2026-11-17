import httpx2

from config import load_sources
from errors import ToolError, from_http_error, with_retries
from tools import rss, weather

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
    # "does NOT search by topic" -> keeps it apart from search_news in Phase 2,
    # where overlapping tools make the description the only way to choose.
    "description": (
        "Get the latest headlines from one news outlet's RSS feed, newest first. "
        "Returns a list of items, each with: title, link (the article URL, to cite "
        "as the source) and published (date string as the outlet gives it, or "
        "\"unknown\"). Use it when the user asks what is in the news, or for "
        "headlines from a specific outlet. Call it once per outlet. "
        "It does NOT search by topic or keyword, and does NOT return the article "
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

    def call():
        try:
            return rss.fetch_feed(FEEDS[source], limit=tool_input.get("limit", 5))
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

# What we send to the API on every call (tool definitions count as input tokens).
TOOLS = [GET_WEATHER_TOOL, FETCH_FEED_TOOL]
# Tool name (what the model asks for) -> adapter (what we run).
# Values are functions, not calls (no parentheses). Keys come from the tool dicts
# so a rename can't break the lookup.
HANDLERS = {
    GET_WEATHER_TOOL["name"]: run_get_weather,
    FETCH_FEED_TOOL["name"]: run_fetch_feed,
}