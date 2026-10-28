# Decisions

Made in the planning chat, 22-28 Oct 2026. Update this file when a decision changes, and say why.

## How we work
- Build from an empty folder, phase by phase, following ROADMAP.md.
- I write the exam-relevant code myself. Claude explains, hints and reviews (see CLAUDE.md).
- The scaffold zip from the very start of the planning chat is NOT used.

## Delivery
- Telegram, one message every day at **09:30 Europe/Belgrade**.
- If it runs on GitHub Actions: cron is in UTC. 09:30 Belgrade = 08:30 UTC in winter (CET),
  07:30 UTC in summer (CEST).

## Content
- Weather: **Novi Sad**, min/max, rain/snow chance (Open-Meteo, free).
- ETFs: **ARKK, BRK.B, SPCX**. Show % move AND price per share. "Important" starts as a daily
  move above 1.5%; refine later. Check every ticker on Yahoo Finance in Phase 2
  (Yahoo writes BRK.B as `BRK-B`).
- FX: **EUR → RSD**, NBS middle rate.
- World outlets: BBC, Guardian, Fox, CNN, Sky News, Al Jazeera.

## News sources
- Serbian news comes from the outlets' **RSS feeds**, from a list I control. That is what keeps
  the brief balanced.
- **Do not use Perplexity** or any other AI search engine as a news source.

## Classifying Serbian media
- Classify outlets by the **camp they are close to**, never as "pro-regime / independent".
  Those labels flip when power changes (Student List won the 25 Oct 2026 election, SNS went
  into opposition; government still being formed as of 28 Oct 2026).
- Camps (my editorial call, review every few months):
  - **SNS camp** (now opposition): Novosti, NewsMax, K1, Euronews
  - **Student camp** (now governing): N1, Danas, Nova, Vreme
  - **Public broadcaster**: RTS — tone tends to follow whoever governs
- **Do not include Informer.**
- Camps + the current government live in `config/sources.yaml`, with a `labels_reviewed` date.
  Example:
  ```yaml
  government:
    current: "Studentska lista"
    since: 2026-10-25
    status: "vlada u formiranju"
  ```
- Whether an article supports or criticises the government is judged **per article** by the
  model (Phase 6, field `framing_toward_government`, "unclear" allowed), not from the outlet name.
- In the brief, use neutral wording ("close to SNS, now opposition"), not "pro-regime".

## X (Twitter) trends — optional Phase 5b
- Only after Phase 5 works.
- X posts are a **signal, never evidence**: an x.com URL can never be the source of a claim
  (enforced in the PreToolUse hook).
- First check that Serbia/Belgrade is an available trends location; skip the phase if not.
- X API is pay-per-use: ~$0.01 per trends request, $0.005 per post read.
