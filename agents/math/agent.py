from __future__ import annotations
import uuid
from orchestrator.router import Router
from shared.schemas import JobContext, Item, Choice
from shared.gemini import call_gemini_json

EVENT_IN = "skill.plan"
EVENT_OUT = "items.math"

SYSTEM = (
    "You are a Year 6 Mathematical Reasoning item writer."
    " Produce multiple-choice questions (5 options: A-E) with a single correct answer and a short solution."
    " Respond ONLY with JSON: {\"items\": [ {prompt, choices:[{id,text}], answer, solution, tags} ] }."
)

PROMPT = (
    "Generate 2 Year 6 math MCQs that require 1–3 steps."
    " Topics: fractions, percentages, ratios, angles, patterns."
    " Constraints: exact numeric answers, plausible distractors, 5 options per item."
)


def _coerce_items(raw_items: list[dict]) -> list[Item]:
    items: list[Item] = []
    labels = ["A", "B", "C", "D", "E"]
    for it in raw_items[:5]:
        prompt = it.get("prompt") or it.get("question") or ""
        choices = it.get("choices") or []
        labeled: list[Choice] = []
        for i, ch in enumerate(choices[:5]):
            if isinstance(ch, dict):
                text = ch.get("text") or ""
                cid = ch.get("id") or labels[i]
            else:
                text = str(ch)
                cid = labels[i]
            labeled.append(Choice(id=cid, text=text))
        for i in range(len(labeled), 5):
            labeled.append(Choice(id=labels[i], text=f"Option {labels[i]}"))
        answer = it.get("answer") or "A"
        solution = it.get("solution") or ""
        tags = it.get("tags") or ["Year6", "math"]
        items.append(
            Item(
                id=str(uuid.uuid4()),
                subject="math",
                prompt=prompt,
                choices=labeled,
                answer=answer,
                solution=solution,
                tags=tags if isinstance(tags, list) else [str(tags)],
            )
        )
    return items


def register(router: Router) -> None:
    async def handle(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        resp = call_gemini_json(PROMPT, system=SYSTEM)
        raw_items = resp.get("items") or []
        items = _coerce_items(raw_items) or [
            Item(
                id=str(uuid.uuid4()),
                subject="math",
                prompt="What is 3/4 of 20?",
                choices=[
                    Choice(id="A", text="15"),
                    Choice(id="B", text="12"),
                    Choice(id="C", text="10"),
                    Choice(id="D", text="5"),
                    Choice(id="E", text="8"),
                ],
                answer="A",
                solution="20 × 3/4 = 15",
                tags=["fractions", "Year6"],
            )
        ]
        await router.emit(EVENT_OUT, {"ctx": ctx.to_dict(), "items": [i.to_dict() for i in items]})

    router.subscribe(EVENT_IN, handle)