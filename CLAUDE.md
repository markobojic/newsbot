# Newsbot

Learning project for the Claude Certified Architect – Foundations exam: a morning news brief
agent that sends me a Telegram message at 08:30.

- Plan: @ROADMAP.md
- Decisions already made (don't re-open them unless I ask): @notes/DECISIONS.md
- My notes and exam traps: @notes/SCRATCHPAD.md
- Exam guide (read the relevant task statement when reviewing): docs/CCA-F-exam-guide.pdf

**Current phase: 0**

## How to help me
- I am learning by writing the code myself.
- For exam-relevant code (tool definitions, the agentic loop, error handling, hooks, schemas,
  prompts, agent configuration): explain the concept, give hints, review my attempt.
  Do NOT write it unless I explicitly say "write it".
- Plumbing the exam doesn't test (RSS parsing, HTTP calls, Telegram formatting, config loading):
  you may write it.
- In reviews, name the exam task statement each point relates to (e.g. "2.2").
- Follow the five steps per phase from ROADMAP.md: Concept → Build → Review → Break it → Check.
- End each phase with 2-3 exam-style multiple-choice questions about MY code, one at a time,
  and wait for my answer.
- When a phase is done, remind me to: update SCRATCHPAD.md, bump "Current phase" above, commit.

## Conventions
- Python 3.11+, virtual env in `.venv/`. Secrets only in `.env` (never commit it).
- Code, comments and file names in English. Reply in the language I write in (Serbian or English).
- Tests must run without network or API key.
