# Newsbot — Build Roadmap

Started Oct 22, 2026 · Marko · Online copy: https://claude.ai/artifact/LsyGVHK3GUosWJ4wFiSZ2E
This file is now the source of truth. Change the plan here, not in two places.

## What you're building

You are building an AI agent that sends you one Telegram message every morning at 09:30. It covers weather, your ETFs, Serbian politics from all sides, and world news, with a source link behind every claim.

The product is the motivation. The real goal is that each feature forces you to make one design decision the exam tests, and you make it yourself, in your own code.

**What the reader gets (you):**

- **Weather** for Novi Sad: min/max, rain/snow chance.
- **Markets**: your ETFs (ARKK, BRK.B, SPCX) with price per share, and EUR to RSD, expanded only when something you care about happened (for example a move larger than 1.5%).
- **Serbia**: the same events as reported by outlets close to SNS, now in opposition (Novosti, NewsMax, K1, Euronews), outlets close to the student movement, now governing (N1, Danas, Nova, Vreme), and the public broadcaster RTS, whose tone tends to follow whoever governs. Where they agree, one line. Where they disagree, both versions side by side, each with its source.
- **World and economy**: 3-5 stories that matter for a reader in Serbia (BBC, Guardian, Fox, CNN, Sky News, Al Jazeera).
- **Coverage notes**: which sources failed today, so you know what the brief could not see.
- **Needs your judgment**: items the agent refuses to conclude on, such as two credible sources stating different facts.

**A finished message looks roughly like this:**

```
Good morning - Thu 22 Oct

WEATHER  Novi Sad 9-17°C, rain 20%

MARKETS
ARKK   +0.3%  $62/share   no notable move
BRK.B  -1.8%  $480/share  watch criterion fired: US CPI release (Guardian)
EUR 117.2 RSD (NBS)

SERBIA
Parliament adopted the 2027 budget (RTS, N1)
Contested: protest in Novi Sad - "several thousand" (N1)
   vs "a few hundred" (Euronews)
Only student-camp outlets covered: ... (Danas)

WORLD
...

ON X
#budzet trending (12k posts) - N1 covered it, SNS camp silent

Coverage notes: Nova feed timed out
Needs your judgment: 1 item
```
(Prices in the sample are made up.)

## How it works

The finished bot is a coordinator that hands research to five specialists running in parallel, then a synthesizer merges their findings, and a hook checks every claim before anything is sent.

```
09:30 schedule ──► COORDINATOR agent ─────────────────────────► get_weather (plain tool, Phase 1)
 (Phase 8)          (Phase 7; one agent in Phases 4-6)
                         │  5 subagent calls in ONE response (parallel)
   ┌──────────┬──────────┼──────────────┬──────────┐
 Markets   SNS camp   Student camp     RTS      World news
 ETFs,     Novosti,   N1, Danas,     public     BBC, Guardian,
 RSD,      K1,        Nova, Vreme    service    Fox, CNN, Sky,
 economy   Euronews                             Al Jazeera
   └──────────┴──────────┼──────────────┴──────────┘
                         │  ResearcherReport JSON: claim, excerpt, URL, date
                  SYNTHESIZER agent  (only tool: verify_fact)
                         │
                PreToolUse hook: deny send if any claim has no source URL (Phase 4)
                         │      (denied → reason goes back, model fixes claims, retries)
                  send_telegram (Phase 5) ──► your Telegram at 09:30
```

Why each piece exists:

- **Coordinator** decides what is needed today and writes complete prompts for the subagents, because subagents don't see its conversation (1.3).
- **Researchers split by camp, not topic.** The SNS camp, the student camp and RTS each get their own agent, so no side can crowd out the others in one context (1.2). Camps don't flip when power changes; who governs is one line in config.
- **Weather is a plain tool call.** Not every task needs an agent.
- **Synthesizer** sees only structured findings and has one narrow tool, so it can't wander off into new research (2.3).
- **The hook** turns "always cite sources" from a request into a guarantee (1.5). A second hook, PostToolUse, rewrites every date into one format before the model sees it.
- **Structured errors** flow upward at every step, so a dead feed becomes a coverage note instead of a silently one-sided brief (5.3).

## How it maps to the exam

| Exam exercise | Phases | Where it lives in the bot | Task statements |
| --- | --- | --- | --- |
| 1. Multi-tool agent with escalation | 1, 2, 4, 5 | Weather, feed, search and market tools; your own agentic loop; structured errors when a feed is down; a hook that blocks unsourced claims; a "needs your judgment" flag | 1.1, 1.4, 1.5, 2.1, 2.2, 5.2 |
| 2. Claude Code team workflow | 3, 8 | CLAUDE.md, path-scoped rules for prompt files, a dry-run skill, `.mcp.json` with the Telegram token as a variable, plan mode, CI review | 3.1-3.6, 2.4 |
| 3. Structured extraction pipeline | 6, 8 | Each article becomes a validated JSON record; retry with the error; Batch API for a weekly report; confidence-based review | 4.1-4.5, 5.5 |
| 4. Multi-agent research pipeline | 7 | Coordinator, parallel researchers split by camp, synthesis that keeps sources and shows conflicts | 1.2, 1.3, 2.3, 5.3, 5.6 |

Exam domain weights: Agentic architecture 27%, Claude Code configuration 20%, Prompt engineering and structured output 20%, Tool design and MCP 18%, Context management and reliability 15%. The full guide is in `docs/CCA-F-exam-guide.pdf`.

## The phases

Each phase is roughly one or two evenings. You get a useful brief on Telegram after Phase 5. Phase 5b is optional.

```
STAGE 1  One agent that works   P0 First API call · P1 Tools and the loop · P2 Tools that fail
STAGE 2  Make it reliable       P3 Claude Code setup · P4 Agent SDK and hooks · P5 Brief on Telegram
         ── gate: a real brief every morning from here on ──
STAGE 3  Scale and automate     P5b X trends (optional) · P6 Structured extraction · P7 Multi-agent · P8 Schedule and CI
```

### Phase 0 - First call

- **Goal:** Claude summarizes 5 headlines from one RSS feed.
- **You build:** `brief.py`, 20 lines: read a feed, call the Messages API, print the answer.
- **You learn:** messages, `system` prompt, `max_tokens`, `stop_reason`, `usage` (tokens = cost).
- **Why now:** everything later is built on this one request/response shape.
- **Done when:** it prints a sourced summary and you can explain every field of the response.

### Phase 1 - First tool and the agentic loop

- **Goal:** Claude decides by itself to call `get_weather` and `fetch_feed`, then answers.
- **You build:** two tools with JSON schemas, and a `while` loop driven by `stop_reason`.
- **You learn:** tool use, `tool_use` vs `end_turn`, returning `tool_result` by id; why parsing the text for "done" is wrong (1.1). Tool descriptions as the model's only guide for choosing (2.1).
- **Why now:** in Phase 0 *you* decided what to fetch. An agent decides itself.
- **Done when:** one question needing both tools works, and you can say why the loop ends.

### Phase 2 - Tools that fail

- **Goal:** the agent stays useful when N1 times out or a site returns 403.
- **You build:** `search_news` (deliberately similar to `fetch_feed`), `get_etf_quotes`, `get_rsd_rates`; a structured error type with category and `is_retryable`; a "chaos" switch to fake outages; `config/sources.yaml` with outlets and camps.
- **You learn:** transient vs validation vs permission vs business errors (2.2); empty result vs failure; what to retry and what to report (5.3); why vague tool descriptions cause wrong tool picks.
- **Why now:** with 5 real tools, some will fail every week. You need this before going multi-agent.
- **Done when:** a faked timeout is retried, a faked 403 is reported, and the brief names the gap.

### Phase 3 - Set up Claude Code for the repo

- **Goal:** Claude Code in VS Code knows your project's conventions and can use your tools.
- **You build:** extend `CLAUDE.md`, `.claude/rules/` with `paths:` for prompt files and tests, a `/brief-dryrun` skill with `context: fork`, `.mcp.json` exposing your tools, a personal MCP server in `~/.claude.json`.
- **You learn:** user vs project vs directory memory (3.1), commands vs skills vs rules (3.2, 3.3), MCP scopes and env variables (2.4), plan mode vs direct execution (3.4).
- **Why now:** the repo now has enough code and conventions that repeating them every session costs you time.
- **Done when:** `/memory` shows your files, rules load only for matching paths, and `/mcp` lists both servers.

### Phase 4 - Agent SDK and hooks

- **Goal:** replace your hand-written loop with the Claude Agent SDK and add guarantees the model can't break.
- **You build:** your tools as an in-process MCP server; a PostToolUse hook that normalizes dates; a PreToolUse hook that denies a send when any claim lacks a source URL.
- **You learn:** prompt instructions are probabilistic, hooks are deterministic (1.4, 1.5); allowed tools and permission modes; sessions, `--resume` and `--fork` (1.7).
- **Why now:** your loop works, so you'll understand what the SDK does for you, and you now have a rule ("always cite") that must never fail.
- **Done when:** with the hook on, no unsourced claim ever reaches the send step, even when you try to provoke one.

### Phase 5 - First real brief on Telegram

- **Goal:** a complete single-agent brief arrives on your phone.
- **You build:** a Telegram bot via @BotFather, a `send_telegram` tool, a `flag_for_review` tool, the full system prompt with explicit escalation rules and examples.
- **You learn:** explicit criteria instead of "flag uncertain things" (4.1, 5.2); few-shot examples for the flag/don't-flag boundary (4.2); keeping tool output small so context doesn't bloat (5.1).
- **Why now:** milestone. From here you use the product daily, and its weaknesses drive Phases 6-7.
- **Done when:** you read it on your phone and every claim has a working link.

### Phase 5b - Trending on X (optional)

- **Goal:** a "Talked about on X" section with Serbian trends, cross-checked against the news.
- **You build:** a `get_x_trends` tool on the X API (pay-per-use, about $0.01 per trends request); a new rule in the PreToolUse hook: an x.com post can never be the source of a claim; a cross-check of which camps covered each trend.
- **You learn:** signal vs evidence and provenance (5.6); a tool description that also says what it does *not* return (2.1); extending a hook with a new rule (1.5).
- **Why now:** only after the core brief works. It's one tool and one section; in Phase 7 it can become a sixth researcher.
- **Before building:** check that Serbia or Belgrade is in X's list of trend locations. If not, skip this phase. Trends alone cost cents a month; reading posts for context costs $0.005 per post.
- **Done when:** the brief shows lines like "#topic is trending; N1 covered it, the SNS camp didn't", and no claim cites an x.com URL.

### Phase 6 - Structured extraction

- **Goal:** each article becomes a validated JSON record: claims, speaker, date, topic, framing toward the government.
- **You build:** a Pydantic schema with nullable fields and "unclear"/"other" options; forced `tool_choice`; a validation-retry loop; field-level confidence; stratified review sampling.
- **You learn:** structured output via tool use (4.3); why required fields cause invented values; what retry can fix and what it can't (4.4); calibrating confidence (5.5).
- **Why now:** the single agent reads full articles into its context. Phase 7's researchers need compact, structured findings to hand over.
- **Done when:** an article with no date gets `null`, not a guess, and a bad enum is fixed on retry.

### Phase 7 - Multi-agent pipeline

- **Goal:** a coordinator runs five researchers in parallel and a synthesizer merges their findings.
- **You build:** subagents for markets, the SNS camp, the student camp, RTS and world news, each with minimal tools; a synthesizer with only a scoped `verify_fact`; prompts for goals, recovery and output format.
- **You learn:** hub-and-spoke orchestration (1.2); subagents don't see the coordinator's context (1.3); tool distribution per role (2.3); error propagation with partial results (5.3); provenance and conflicts (5.6).
- **Why now:** one agent reading 15 outlets runs out of context and tends to favor whichever side published more.
- **Done when:** with one camp's feeds all faked as down, the brief still goes out with the gap named, and a real conflict shows both sides.

### Phase 8 - Production

- **Goal:** it runs every morning without you and stays reviewable.
- **You build:** a scheduled job (GitHub Actions or cron), run logs, a CI step that runs `claude -p` to review prompt changes, a weekly "how each outlet framed the week" report on the Batch API.
- **You learn:** CI mode and JSON output (3.6); independent review instances (4.6); when batch is right and when it isn't (4.5); crash recovery from saved state (5.4).
- **Why now:** a bot you have to start by hand isn't a product.
- **Done when:** a week of briefs arrive at 09:30 without you touching anything.

## How the project grows

```
newsbot/
├── brief.py                      P0  first call (later becomes main.py)
├── .env  .gitignore              P0  API key, never committed
├── tools/
│   ├── weather.py  rss.py        P1  plain Python, no Claude inside
│   └── markets.py                P2
├── loop.py                       P1  your hand-written agentic loop
├── errors.py                     P2  structured tool errors
├── config/sources.yaml etfs.yaml P2  outlets, camps, your ETFs
├── CLAUDE.md                     P0→ project memory for Claude Code (extended in P3)
├── .claude/rules/ skills/        P3  path rules, /brief-dryrun
├── .mcp.json  mcp_server.py      P3  your tools inside Claude Code
├── sdk_tools.py  hooks.py        P4  Agent SDK server and hooks
├── prompts/single_agent.md       P5  prompts live in files, not code
├── tools/telegram.py             P5
├── tools/x_trends.py             P5b optional
├── schemas.py  extract.py        P6  Pydantic contracts, retry, batch
├── agents.py  coordinator.py     P7  subagents and orchestration
├── prompts/coordinator.md ...    P7
├── tests/                        P1+ grows with every phase, no network needed
├── notes/SCRATCHPAD.md           P0+ your observations and exam traps
└── .github/workflows/            P8  schedule and CI review
```

**Stack:** Python 3.11+, `anthropic` (Phases 0-2, 6), `claude-agent-sdk` (Phases 4-8), `feedparser`, `httpx`, `pydantic`, `pytest`. Data sources: Open-Meteo for weather, outlet RSS feeds, a Yahoo chart endpoint for ETFs, NBS rates for RSD, X API (optional, paid).

## How we work each phase

Every phase runs the same five steps: you write the code that matters for the exam, and Claude acts as mentor and reviewer, not as the author.

1. **Concept** - what the phase is about, which task statements it covers, and the exam trap hiding in it.
2. **Build** - you write the code. Hints and API details when you're stuck, not the solution. Plumbing the exam doesn't test (RSS parsing, Telegram formatting) can be given as ready snippets.
3. **Review** - Claude reviews your code like a senior colleague and points each comment to its task statement.
4. **Break it** - break it on purpose: remove a hook, fake an outage, blur a tool description. Seeing the failure is what makes the right answer stick.
5. **Check** - 2-3 exam-style questions about your own code, then move on.

**Rules of thumb:**

- Write observations in `notes/SCRATCHPAD.md` as you go, especially the traps you fall into. That file becomes your revision sheet before the exam.
- Don't skip "Break it". Most exam questions describe a broken system and ask for the best fix.
- If a phase takes longer than two evenings, cut scope without losing the exam topic.

## Before you start

**Your decisions:** see `notes/DECISIONS.md`.

**To prepare:**

- [ ] An Anthropic API key with a small monthly spend limit (measure the real cost per brief from `usage` in Phase 0)
- [ ] Python 3.11+, VS Code, and the Claude Code extension
- [ ] Your ETF tickers as Yahoo Finance symbols (check each one)
- [ ] A Telegram account (the bot itself is created in Phase 5)
