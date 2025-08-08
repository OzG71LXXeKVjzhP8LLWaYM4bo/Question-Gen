# Question-Gen

Year 6 selective exam question generator powered by Gemini and simple agent-to-agent (A2A) orchestration.

## What it does
- Generates multiple-choice questions for three sections: Thinking Skills, Mathematical Reasoning, and Reading.
- Uses Gemini (via `GEMINI_API_KEY`) to draft questions; falls back to safe stubs if the key/model is not available.
- Validates items and saves them as JSON under `questions/{subject}/...` (ignored by git).
- All MCQs use 5 options (A–E) with a single correct answer.

## Quickstart
1. Python 3.13+
2. Using uv (recommended):
   ```bash
   uv venv      # optional: create .venv
   uv sync      # install deps from pyproject/uv.lock
   ```
3. Create `.env` in the repo root:
   ```env
   GEMINI_API_KEY=YOUR_KEY
   # Optional model (pick what you have access to)
   GEMINI_MODEL=models/gemini-2.5-pro
   # or: GEMINI_MODEL=models/gemini-2.0-flash
   ```
4. Run:
   ```bash
   uv run python main.py
   ```
   You should see lines like:
   ```
   VALIDATED: 2 items
   saved: questions/thinking/<job>_<ts>.json
   VALIDATED: 2 items
   saved: questions/math/<job>_<ts>.json
   VALIDATED: 2 items
   saved: questions/english/<job>_<ts>.json
   ```
5. Alternative without uv:
   ```bash
   pip install python-a2a python-dotenv
   python main.py
   ```

## Repository layout
```
Question-Gen/
  agents/
    english/agent.py      # Reading items (5-option MCQs)
    math/agent.py         # Math reasoning items (5-option MCQs)
    thinking/agent.py     # Thinking Skills items (5-option MCQs) + emits a skill plan
    validator/agent.py    # Pass-through validator placeholder
  orchestrator/
    router.py             # In-process async event bus
    jobs.py               # Emits initial topic event
  shared/
    schemas.py            # Dataclass message contracts (JobContext, Item, Choice, ...)
    config.py             # Defaults (e.g., choices=5)
    gemini.py             # Minimal Gemini HTTP client (JSON responses)
    storage.py            # Saves validated items under questions/{subject}/
  questions/              # Generated JSON files (git-ignored)
  main.py                 # Wires agents, runs a demo job
  .env                    # Put GEMINI_API_KEY here
```

## How it works (A2A flow)
- `topic.received` → `agents/thinking` creates a short `skill.plan` and Thinking items.
- `skill.plan` → `agents/math` and `agents/english` generate items.
- `items.*` → `agents/validator` emits `items.validated`.
- `main.py` listens to `items.validated`, prints counts, and saves JSON via `shared/storage.py`.

## Configuration knobs
- 5-option MCQ policy: set in `shared/config.py` (`choices=5`) and enforced in each agent’s coercion logic.
- Item counts and types: adjust prompt strings in `agents/*/agent.py` (`PROMPT`/`SYSTEM`).
- Model selection: set `GEMINI_MODEL` in `.env`.

## Notes
- `questions/english/`, `questions/math/`, and `questions/thinking/` are ignored by git (see `.gitignore`).
- The current validator is minimal; you can add numeric checks, quote-support checks, and dedupe in `agents/validator/agent.py`.

## License
MIT (see `LICENSE`).
