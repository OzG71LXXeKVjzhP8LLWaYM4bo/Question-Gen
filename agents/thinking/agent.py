from __future__ import annotations
import uuid
import asyncio
from orchestrator.router import Router
from shared.schemas import JobContext, Item, Choice
from shared.gemini import call_gemini_json_async

EVENT_IN = "topic.received"
EVENT_OUT_PLAN = "skill.plan"
EVENT_OUT_ITEMS = "items.thinking"

SYSTEM_PLAN = (
    "You design Year 6 selective exam reasoning plans."
    " Return compact JSON with key skill_plan as a list of objects with keys: skill, steps."
)

PROMPT_PLAN = (
    "Topic: {topic}\n"
    "Grade: Year 6\n"
    "Create a minimal skill_plan (1-2 entries) focusing on multi-step reasoning."
)

SYSTEM_ITEMS = (
    "You are a Year 6 Thinking Skills item writer for selective tests."
    " Create multiple-choice questions with 5 options (A-E), exactly one correct."
    " Keep language simple; require reasoning (not background knowledge)."
    " Types: analogies, pattern completion, ordering/ranking, logical deduction."
    " Respond ONLY with JSON: {\"items\":[{prompt, choices:[{id,text}], answer, solution, tags}]}"
)

PROMPT_ITEMS = (
    "Generate 2 Year 6 Thinking Skills MCQs covering two different types"
    " from: analogies, pattern completion, ordering/ranking, logical deduction."
    " Provide 5 options per item."
)


def _coerce_items(raw_items: list[dict]) -> list[Item]:
    items: list[Item] = []
    labels = ["A", "B", "C", "D", "E"]
    for it in raw_items[:5]:
        prompt = it.get("prompt") or it.get("question") or ""
        choices = it.get("choices") or []
        labeled: list[Choice] = []
        for i, ch in enumerate(choices[:5]):
            text = ch.get("text") if isinstance(ch, dict) else str(ch)
            cid = ch.get("id") if isinstance(ch, dict) else labels[i]
            labeled.append(Choice(id=cid or labels[i], text=text))
        for i in range(len(labeled), 5):
            labeled.append(Choice(id=labels[i], text=f"Option {labels[i]}"))
        items.append(
            Item(
                id=str(uuid.uuid4()),
                subject="thinking",
                prompt=prompt,
                choices=labeled,
                answer=it.get("answer", "A"),
                solution=it.get("solution", ""),
                tags=it.get("tags", ["Year6", "thinking"]),
            )
        )
    return items


def register(router: Router) -> None:
    async def handle(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        topic = msg.get("topic", "general reasoning")
        # Run plan and items in parallel
        plan_task = asyncio.create_task(
            call_gemini_json_async(PROMPT_PLAN.format(topic=topic), system=SYSTEM_PLAN)
        )
        items_task = asyncio.create_task(
            call_gemini_json_async(PROMPT_ITEMS, system=SYSTEM_ITEMS)
        )
        plan_resp, items_resp = await asyncio.gather(plan_task, items_task)
        # Emit plan
        plan = plan_resp.get("skill_plan") if isinstance(plan_resp, dict) else None
        if not plan:
            plan = [
                {"skill": "multi-step reasoning", "steps": ["identify", "compute", "check"]}
            ]
        await router.emit(EVENT_OUT_PLAN, {"ctx": ctx.to_dict(), "skill_plan": plan})
        # Emit items
        raw_items = items_resp.get("items") if isinstance(items_resp, dict) else []
        items = _coerce_items(raw_items) or [
            Item(
                id=str(uuid.uuid4()),
                subject="thinking",
                prompt="Which figure comes next in the pattern? (use text description)",
                choices=[
                    Choice(id="A", text="Pattern continues by adding one dot"),
                    Choice(id="B", text="Pattern removes one dot"),
                    Choice(id="C", text="Pattern mirrors horizontally"),
                    Choice(id="D", text="Pattern rotates 90 degrees"),
                    Choice(id="E", text="Pattern repeats from start"),
                ],
                answer="A",
                solution="Each step adds one dot; next has one more dot than previous.",
                tags=["pattern", "Year6"],
            )
        ]
        await router.emit(EVENT_OUT_ITEMS, {"ctx": ctx.to_dict(), "items": [i.to_dict() for i in items]})

    router.subscribe(EVENT_IN, handle)