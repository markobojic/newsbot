# Phase 2 plan: tools that fail

## Concept (what the phase teaches)

Right now `loop.py` runs `HANDLERS[block.name](block.input)` with no protection. If a feed is
down, the whole run crashes, the weather you already fetched is lost, and the model never learns
what happened. Phase 2 changes this: **a failure becomes data that the model can reason about**.

| Task statement | What you'll practice |
|---|---|
| **2.1** | Tool descriptions when two tools overlap (`fetch_feed` vs `search_news`) |
| **2.2** | Structured errors: category (transient / validation / permission / business) plus `is_retryable` |
| **5.3** | Empty result vs failure, partial results, naming the gap instead of hiding it |

**The exam trap:** these four answers are all wrong:
- an empty list `[]` when the call actually failed. The model then reports "no news today",
  which is a lie.
- a generic `"error": "failed"`. The model can't tell whether to retry.
- retrying everything, including a 403 that will never succeed.
- stopping the whole run because one source failed.

The right answer is a structured error, local retry only for transient failures, and passing up
what can't be fixed so it shows in the output.

---

## Build order

### Step 1: Move tool definitions out of `loop.py` (refactor, you)
Create `tools/registry.py` (or a name you prefer) to hold the `*_TOOL` dicts, the adapters,
`TOOLS` and `HANDLERS`. `loop.py` keeps only the loop.

**Why it matters later:** Phase 3 (`mcp_server.py`) and Phase 4 (`sdk_tools.py`) wrap the
**same** definitions. If they live in `loop.py`, you'll end up with three copies that drift apart.

### Step 2: `config/sources.yaml` + `config/holdings.yaml` + a loader (plumbing, Claude can write it)
- Outlets with `camp: sns | student | public | world`, feed URL, and `language`. Plus
  `government:` and `labels_reviewed:` as in DECISIONS.md. No Informer.
- Holdings: `ARKK`, `BRK-B` (Yahoo symbol) with the display name `BRK.B`, and `SPCX` (check it
  on Yahoo first).
- The `source` enum in `fetch_feed` is **generated from the yaml**, the same pattern as
  `CITIES`/`FEEDS`.

**Why it matters later:** in Phase 7 each researcher gets `outlets where camp == X` from this
file, so camps aren't hardcoded in prompts. When power changes, you edit one line. Phase 6's
`framing_toward_government` reads `government.current` from here.

### Step 3: `errors.py`, the structured error type (**you write it, exam core**)
It needs:
- `category`: transient / validation / permission / business
- `is_retryable`: bool
- `message`: human-readable, for the model
- `source`: which outlet or ticker failed

It also needs a function that maps a real exception to a category. Work out which category each
case belongs to: `httpx` timeout, 5xx, 429, 401/403, 404, a feed that won't parse, unknown
ticker, input outside the enum.

**Key distinction:** a successful empty result (`{"items": [], ...}`) is **not** an error. Make
sure the model sees the difference.

**Why it matters later:** Phase 4 hooks and MCP return `isError` with this same payload. In
Phase 7 every researcher returns these errors to the coordinator, which decides whether to retry
or turn the error into a **coverage note** (5.3). The shape you define now becomes the contract
between agents.

### Step 4: Error handling in the loop (**you, exam core**)
- Wrap the handler call in `try/except` and return a `tool_result` with `is_error: true` and the
  structured error as content.
- An unknown tool name also gets a `tool_result`, so every `tool_use` must get an answer
  (a trap from Phase 1).
- **Decide yourself where retries live:** in the tool layer (bounded, with backoff) or by letting
  the model call again? Hint: the exam favors local recovery for transient errors and passing up
  only what can't be fixed. Record your decision and the reason in SCRATCHPAD.
- Remember that the Anthropic SDK retries **its own** API calls, but not your `httpx` calls to
  RSS, Yahoo or NBS.

### Step 5: Chaos switch (plumbing, Claude can write it, but design the interface together)
For example, an env variable `CHAOS="n1:timeout,danas:403,yahoo:429"` that makes the HTTP layer
raise the matching exception before any network call.

**Why it matters later:** it powers "Break it" in this phase, the "one camp completely down"
scenario in Phase 7's Done-when, and tests that run without network.

### Step 6: Three new tools
Rule of thumb: the HTTP and parsing code is plumbing, so Claude can write it. The **tool
definitions (name, description, schema)** and **adapters** are yours.

**a) `search_news(query, camp?, hours?)`** searches by keyword across items from the
**configured** feeds (no Perplexity, no external search engine, per DECISIONS). It is
deliberately close to `fetch_feed`.
- **Lesson 2.1:** only the description tells the model when to use "headlines from one outlet"
  and when to use "find a topic across outlets". Use the description to separate them clearly.
- **Lesson 5.3 in miniature:** it reads 4 feeds and 1 fails. The result is partial: what was
  found plus a list of sources that failed. Neither "error" nor quietly returning 3/4 is correct.
- **Later:** this is the main tool for the Phase 7 camp researchers, used to find **the same
  event** across camps. That makes the "Contested: protest in Novi Sad" line possible (5.6).

**b) `get_holdings_quotes()`** uses the Yahoo chart endpoint and returns price, % change,
currency, and `as_of`.
- Real-world lesson: the unofficial endpoint often returns 429, which is your first real
  transient error. A ticker Yahoo doesn't recognize is a validation or business error, not
  retryable.
- On a weekend the market is closed. That is **not** an error: the data is valid but stale, and
  `as_of` says so.
- **Later:** used by the Markets researcher (Phase 7), and the source for the explicit criterion
  "move > 1.5%" (Phase 5, 4.1).

**c) `get_rsd_rates()`** returns the NBS middle EUR→RSD rate along with the date of the rate.
- On weekends and holidays NBS doesn't publish a new rate. Again, return the last rate with its
  date, not an error.
- Check first which source we use. NBS doesn't offer a simple free JSON endpoint, so decide on a
  source together during Build.
- **Later:** the "EUR 117.2 RSD (NBS)" line in the brief, and part of the Markets researcher.

### Step 7: Tests (no network)
- Error classification for each case in step 3.
- Loop with a fake `client` and a fake handler that raises: the next request must contain
  `is_error`, and the loop must keep going.
- Unknown tool name.
- Chaos: `n1:timeout` produces transient and retryable; `danas:403` produces permission and not
  retryable.
- `search_news` with 1 of 4 feeds down returns partial results plus a list of failed sources.

---

## Break it
1. Return `[]` instead of an error when a feed fails. Does the model say "no news"?
2. Remove `is_retryable` and the category, leaving only `"error": "failed"`. What does the model
   do with a 403?
3. Blur the `search_news` description so it reads like `fetch_feed`. Does it now pick the wrong
   tool? (In Phase 1 this didn't show up because the tools didn't overlap.)
4. Raise inside the handler without `try/except`. You've already seen the crash; now you'll see
   the difference.
5. Faked 403 and timeout at once. Is only the timeout retried?

## Done when (from the ROADMAP)
- [x] A faked timeout is retried (you can see the attempts in the log).
- [x] A faked 403 is **not** retried, and the model reports it.
- [x] The final answer names the gap ("Nova unavailable today").
- [x] `pytest` passes without network and without an API key.

## Progress
- [x] Step 1: refactor tool definitions out of `loop.py`
- [x] Step 2: `config/sources.yaml`, `config/holdings.yaml`, loader
- [x] Step 3: `errors.py`
- [x] Step 4: error handling + retry policy in the loop
- [x] Step 5: chaos switch
- [x] Step 6a: `search_news`
- [ ] Step 6b: `get_holdings_quotes`
- [ ] Step 6c: `get_rsd_rates`
- [ ] Step 7: tests
- [ ] Break it
- [ ] Check (2-3 exam questions)
