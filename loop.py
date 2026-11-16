"""Phase 1: hand-written agentic loop with two tools."""

import json

import anthropic
from dotenv import load_dotenv

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
    lat, lon = CITIES[tool_input["city"]]
    return weather.get_forecast(lat, lon, days=tool_input.get("days", 1))


# --- Tool 2: fetch_feed -------------------------------------------------------
# Feed URLs live in code, from a list I control (DECISIONS.md): the model never
# invents a URL. Same pattern as CITIES.
FEEDS = {
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian_world": "https://www.theguardian.com/world/rss",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}

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
                "description": "Outlet to read, e.g. \"bbc_world\".",
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
    url = FEEDS[tool_input["source"]]
    return rss.fetch_feed(url, limit=tool_input.get("limit", 5))


# --- Loop configuration -------------------------------------------------------
MODEL = "claude-haiku-5-5"
# Safety net against a runaway loop (and a runaway bill). NOT how the loop
# normally ends: that is end_turn. Hitting this cap means something is wrong (1.1).
MAX_ITERATIONS = 10
# What we send to the API on every call (tool definitions count as input tokens).
TOOLS = [GET_WEATHER_TOOL, FETCH_FEED_TOOL]
# Tool name (what the model asks for) -> adapter (what we run).
# Values are functions, not calls (no parentheses). Keys come from the tool dicts
# so a rename can't break the lookup.
HANDLERS = {
    GET_WEATHER_TOOL["name"]: run_get_weather,
    FETCH_FEED_TOOL["name"]: run_fetch_feed,
}


def run(question: str) -> str:
    """Run the agentic loop until the model ends its turn; return its text answer."""
    load_dotenv()  # puts ANTHROPIC_API_KEY into the environment
    client = anthropic.Anthropic()
    # The whole conversation. The API is stateless, so every call resends all of it
    # and input tokens grow each step.
    messages = [
        {"role": "user", "content": question},
    ]
    for _ in range(MAX_ITERATIONS):
        # 1. Call the model. With tools=..., it may answer OR ask for tools.
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,  # includes thinking tokens; too low -> stop_reason max_tokens
            tools=TOOLS,
            messages=messages
        )

        # 2. Decide by stop_reason, never by parsing the text (1.1).
        # end_turn = the MODEL decided it has everything and is done -> normal exit.
        if response.stop_reason == "end_turn":
            # content is a list of blocks; keep only text (skip thinking etc.).
            texts = [block.text for block in response.content if block.type == "text"]
            return "".join(texts)

        # Anything other than tool_use (max_tokens, refusal, ...) is not a valid
        # result: fail loudly instead of returning a half answer.
        if response.stop_reason != "tool_use":
            raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")

        # 3. stop_reason == tool_use -> the loop CONTINUES.
        # Append the model's turn unchanged (thinking blocks included). Every
        # tool_result must answer a tool_use from the turn right before it.
        messages.append({"role": "assistant", "content": response.content})

        # 4. WE run the tools (the model never runs code). One response can hold
        # several tool_use blocks; answer every one of them.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                # Phase 1 gap: an exception here (feed down) or an unknown name
                # (KeyError) crashes run(). Phase 2: catch it, send is_error (2.2).
                output = HANDLERS[block.name](block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,  # links this result to its request
                    "content": json.dumps(output),  # content must be a string
                })
        # 5. All results go back in ONE user turn, then loop: the model now sees
        # question -> its tool request -> our results.
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"No final answer after {MAX_ITERATIONS} steps")


if __name__ == "__main__":
    answer = run("What's the weather in Novi Sad today, and what are the top world headlines from BBC?")
    print(answer)
