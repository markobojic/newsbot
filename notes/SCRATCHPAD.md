# Scratchpad

Short, dated notes. This becomes my revision sheet before the exam.

## Phase log
| Phase | Finished | What I learned | Trap I fell into |
|---|---|---|---|
| 0 | 2026-11-16 (Check skipped) | One Messages API request/response: `model`, `max_tokens`, `system`, `messages` in; `content`, `stop_reason`, `usage` out | `create({})` - SDK takes keyword args only. `max_tokens=500` cut the answer off because thinking used 319 of the 500 tokens |
| 1 | 2026-11-16 (Break it: only #4; Check skipped) | Tool definitions (name/description/input_schema) and a hand-written loop driven by `stop_reason`; the model asks, MY code runs the tool | Thought the loop stops on `tool_use`. It's the opposite: `tool_use` = continue, `end_turn` = stop. Forgot the assistant turn sits between question and tool_results |
| 2 | | | |

## Phase 0 notes (2026-11-16)

**Request (`client.messages.create`)**
- `model` - which model answers. Kept in a constant so I can swap and compare cost/quality.
- `max_tokens` - upper limit on OUTPUT tokens, not a target. Includes thinking tokens.
- `system` - top-level parameter for role + rules + format. No `role: "system"` message exists.
- `messages` - list of turns, starts with `user`, then alternates `user`/`assistant`.
  The API is stateless: every call resends the whole history (input tokens grow each step).
- Data (headlines) goes in the user message; rules go in the system prompt.

**Response**
- `content` - a LIST of blocks, each with `.type`. Seen so far: `thinking`, `text`.
  Phase 1 adds `tool_use`. Never `content[0].text` - loop and filter by `.type`.
- `stop_reason` - why the model stopped:
  `end_turn` (finished), `max_tokens` (cut off), `tool_use` (wants a tool, P1),
  `stop_sequence`, `refusal`.
- `usage` - `input_tokens`, `output_tokens` (= cost). `output_tokens_details.thinking_tokens`
  is part of output and billed at the output price.

**Client**
- `anthropic.Anthropic()` reads `ANTHROPIC_API_KEY` from env -> call `load_dotenv()` first.
- Creating the client does no network call; a bad key shows up as 401 on the first request.
- Create one client and pass it in (reuse connections, testable with a fake).
- SDK already retries connection errors, 429 and 5xx (2x by default) - remember in Phase 2.

**System prompt structure (4 parts)**
1. Role + goal (who reads it and why)
2. Rules as checkable criteria ("link at end of every bullet", not "be accurate")
3. Edge cases - what to do instead of guessing ("mark it (unclear from headline)")
4. Output format (length, structure, language, "no introduction")

**Plumbing note**
- macOS python.org Python: feedparser's urllib fails with CERTIFICATE_VERIFY_FAILED.
  Fetch with `httpx2` (system trust store), then `feedparser.parse(resp.content)`.

## Phase 1 notes (2026-11-16)

**Tool definition = all the model knows (2.1)**
- Only `name`, `description`, `input_schema` reach the model. Python code and docstrings don't.
- Good description: what it returns (fields + units), when to use it, what it does NOT do,
  what to do for unsupported input ("say it is not supported, don't pick the nearest city").
- `enum` for inputs I control (cities, feed sources): the model can't invent a URL or
  coordinates. Lookup tables (`CITIES`, `FEEDS`) live in code.
- `input_schema` guides, it doesn't guarantee (strict mode: Phase 6). Optional fields
  get their default in the adapter (`tool_input.get("days", 1)`).
- Tool interface != Python signature (city name vs lat/lon). An adapter bridges them.
- Tool definitions are sent on every call and count as input tokens (~1000 for 2 tools).

**The loop (1.1)**
1. Call with `tools=TOOLS`.
2. `end_turn` -> return text blocks (the MODEL decided it's done = the only normal exit).
3. Not `tool_use` (`max_tokens`, `refusal`) -> raise, it's not a valid result.
4. `tool_use` -> append `response.content` unchanged as the assistant turn.
5. Run EVERY `tool_use` block via `HANDLERS[block.name](block.input)`.
6. All `tool_result`s (`tool_use_id`, `json.dumps(...)` as content) in ONE user turn. Loop.
- `HANDLERS` = tool name -> function (not a call). Keys from the tool dicts so they can't drift.
- One response can hold several `tool_use` blocks (weather + feed came together).
- `messages` grows: `[user question, assistant tool_use x2, user tool_result x2]`.
  The API is stateless, so input went 1025 -> 1863 tokens on the 2nd call.
- `MAX_ITERATIONS` is a safety net against a runaway loop/bill, not the stop condition.

**Break it**
- #4 vague descriptions ("Gets data."): nothing changed. Tool names + enums still told the
  model everything, and the two tools don't overlap. Descriptions decide when tools overlap
  (Phase 2 `search_news`) and in edge cases (Niš: not supported vs silently use Belgrade).
- Not done: drop the assistant append, BBC feed 404, `max_tokens=100`, Niš test.

**Observed**
- Claude dropped `?at_medium=RSS&at_campaign=rss` from BBC links: it changed the source URL
  without being asked. A prompt rule only asks; a hook guarantees (Phase 4, 1.4/1.5).

**Known gaps for Phase 2 (2.2, 5.3)**
- A tool that raises (feed down) crashes `run()`: no retry, the weather that worked is lost,
  and the model never learns what failed. Fix: catch it, send `tool_result` with `is_error`.
- Unknown tool name -> `KeyError`. Every `tool_use` must still get a `tool_result`.
- First step of Phase 2: move tool definitions + adapters + HANDLERS to their own module
  (`loop.py` keeps only the loop; MCP server and SDK will reuse the same definitions).

## Exam traps (collected)
- Decide by `stop_reason`, never by parsing the text (1.1). `max_tokens` = truncated answer,
  treat as a failure, not a valid result.
- `system` is a separate parameter, not a message role.
- `content` is a list of blocks; the first block may be `thinking` or `tool_use`, not text.
- Thinking tokens count toward `max_tokens` and are billed as output.
- A rule in the system prompt is a request (probabilistic). A rule that must never fail
  needs a hook (Phase 4, 1.4/1.5).
- Vague instructions ("flag uncertain things") -> explicit criteria instead (4.1, 5.2).
- `tool_use` = loop continues, `end_turn` = loop stops. The model decides when it's done (1.1).
- An iteration cap is a safety net, never the main stop condition. "Stop after N rounds" and
  "stop when the text says done" are wrong answers (1.1).
- Every `tool_result` needs the matching `tool_use` in the assistant turn right before it;
  append `response.content` unchanged (thinking blocks included).
- Several `tool_use` blocks in one response -> all results in ONE user message, matched by id.
- Wrong tool picked -> first fix the tool description, not the system prompt (2.1).

## Costs
| Date | Run | Input tokens | Output tokens | Cost |
|---|---|---|---|---|
| 2026-11-16 | brief.py, BBC World, 5 items, max_tokens=500 (cut off) | 767 | 500 (319 thinking) | TODO: price x tokens |
| 2026-11-16 | brief.py, BBC World, 5 items, max_tokens=2000 | 767 | 636 (238 thinking) | TODO: price x tokens |
| 2026-11-16 | loop.py, weather + BBC, 2 calls (1025 + 1863 in, 147 + 510 out) | 2888 | 657 | TODO: price x tokens |
