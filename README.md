# Question-Gen

Year 6 selective exam question generator powered by Gemini and simple agent-to-agent (A2A) orchestration.

## What it does
- Generates multiple-choice questions for three sections: Thinking Skills, Mathematical Reasoning, and Reading.
- Uses Gemini (via `GEMINI_API_KEY`) to draft questions; falls back to safe stubs if the key/model is not available.
- Validates items using structural checks + Gemini semantic validation; only passing items are saved.
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
4. CLI demo (one item per subject):
   ```bash
   uv run python main.py
   ```
   You should see lines like:
   ```
   VALIDATED: 1 items
   saved: questions/thinking/<job>_<ts>.json
   VALIDATED: 1 items
   saved: questions/math/<job>_<ts>.json
   VALIDATED: 1 items
   saved: questions/english/<job>_<ts>.json
   ```
5. API server (FastAPI):
   ```bash
   uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
   ```
   - Endpoint: `POST /generate`
   - Request JSON (single subject only):
     ```json
     { "subject": "math" }
     ```
   - Behavior: picks a random seed topic from that subject’s curriculum, generates and validates 1 item, returns:
     ```json
     { "items": [/* validated items */], "failed": [/* failures, if any */] }
     ```

## Repository layout
```
Question-Gen/
  agents/
    english/agent.py      # Reading items (5-option MCQs) + emits skill.plan.english
    math/agent.py         # Math reasoning items (5-option MCQs) + emits skill.plan.math
    thinking/agent.py     # Thinking Skills items (5-option MCQs) + emits a generic skill.plan
    validator/agent.py    # Structural + Gemini validation; emits items.validated
  orchestrator/
    router.py             # In-process async event bus
    jobs.py               # Emits initial topic event
  shared/
    schemas.py            # Dataclass message contracts (JobContext, Item, Choice, ...)
    config.py             # Defaults (e.g., choices=5)
    gemini.py             # Async Gemini HTTP client (httpx), JSON responses
    storage.py            # Saves validated items under questions/{subject}/
    topics.py             # Subject-specific topic pools (randomized selection)
  api/
    app.py                # FastAPI app exposing POST /generate
  questions/              # Generated JSON files (git-ignored)
  main.py                 # Wires agents, runs a demo job
  .env                    # Put GEMINI_API_KEY here
```

## How it works (A2A flow)
- `topic.received` → planners:
  - `agents/thinking` emits `skill.plan` and also generates `items.thinking`
  - `agents/math` emits `skill.plan.math`
  - `agents/english` emits `skill.plan.english`
- Generators consume subject plans (one item per subject by default):
  - `agents/math` listens to `skill.plan.math` → emits `items.math`
  - `agents/english` listens to `skill.plan.english` → emits `items.english`
  - `agents/thinking` directly emits `items.thinking`
- Validation and storage:
  - `agents/validator` performs structural checks and Gemini semantic validation, then emits `items.validated` with:
    - `items`: only the items that passed
    - `failed`: list of failures with reasons (for review)
  - `main.py` listens to `items.validated`, prints counts, and saves JSON via `shared/storage.py`

## Validator rules (current)
- Structural checks:
  - Exactly 5 choices labeled A, B, C, D, E (in order)
  - Answer in A–E, non-empty prompt and choice texts
- Gemini checks:
  - Single correct answer; correctness of the provided answer
  - For math: recomputation; for reading/thinking: unambiguity/plausibility
- Output: passes are saved; failures included in the event payload `failed` (not saved)

## Performance
- Gemini calls are asynchronous (httpx). Thinking runs plan + items in parallel; Math/English plan and generate concurrently from `topic.received`.
- To generate more per call, increase requested item counts in each agent’s prompts.

## Configuration knobs
- 5-option MCQ policy: set in `shared/config.py` (`choices=5`) and enforced in each agent’s coercion logic.
- Subject-specific planning: Math/English each emit and consume their own plans (`skill.plan.math`, `skill.plan.english`).
- Random topics: each agent samples two topics from `shared/topics.py` and instructs Gemini to integrate both.
- Model selection: set `GEMINI_MODEL` in `.env`.

## Notes
- `questions/english/`, `questions/math/`, and `questions/thinking/` are ignored by git (see `.gitignore`).
- The validator currently returns a minimal report; extend it to enforce reading-level, dedupe, or numeric solvers if needed.

## License
MIT (see `LICENSE`).
