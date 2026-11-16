# Scratchpad

Short, dated notes. This becomes my revision sheet before the exam.

## Phase log
| Phase | Finished | What I learned | Trap I fell into |
|---|---|---|---|
| 0 | 2026-11-16 (Check skipped) | One Messages API request/response: `model`, `max_tokens`, `system`, `messages` in; `content`, `stop_reason`, `usage` out | `create({})` - SDK takes keyword args only. `max_tokens=500` cut the answer off because thinking used 319 of the 500 tokens |
| 1 | | | |

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

## Exam traps (collected)
- Decide by `stop_reason`, never by parsing the text (1.1). `max_tokens` = truncated answer,
  treat as a failure, not a valid result.
- `system` is a separate parameter, not a message role.
- `content` is a list of blocks; the first block may be `thinking` or `tool_use`, not text.
- Thinking tokens count toward `max_tokens` and are billed as output.
- A rule in the system prompt is a request (probabilistic). A rule that must never fail
  needs a hook (Phase 4, 1.4/1.5).
- Vague instructions ("flag uncertain things") -> explicit criteria instead (4.1, 5.2).

## Costs
| Date | Run | Input tokens | Output tokens | Cost |
|---|---|---|---|---|
| 2026-11-16 | brief.py, BBC World, 5 items, max_tokens=500 (cut off) | 767 | 500 (319 thinking) | TODO: price x tokens |
| 2026-11-16 | brief.py, BBC World, 5 items, max_tokens=2000 | 767 | 636 (238 thinking) | TODO: price x tokens |
