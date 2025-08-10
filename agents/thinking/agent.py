from __future__ import annotations
import uuid
import asyncio
from orchestrator.router import Router
from shared.schemas import JobContext, Item, Choice
from shared.gemini import call_gemini_json_async
from shared.topics import THINKING_TOPICS
import random

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
    "Generate 1 Year 6 Thinking Skills MCQ that requires multi-step reasoning"
    " and integrates both topics: {topic_a} and {topic_b}."
    " Choose from analogies, pattern completion, ordering/ranking, or logical deduction."
    " Provide 5 options per item."
    " Target difficulty level: {difficulty} (1 easy, 2 medium, 3 hard)."
)


def _coerce_items(raw_items: list[dict]) -> list[Item]:
    items: list[Item] = []
    labels = ["A", "B", "C", "D", "E"]
    if not isinstance(raw_items, list):
        return []
    for it in raw_items[:1]:
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
                difficulty=int(it.get("difficulty", 2)) if isinstance(it, dict) else 2,
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
        # Retry items up to 2 times
        async def _gen_items() -> list[Item]:
            temps = [0.5, 0.8]
            topic_a, topic_b = random.sample(THINKING_TOPICS, 2)
            difficulty = int(ctx.constraints.get("difficulty", 2)) if isinstance(ctx.constraints, dict) else 2
            prompt = PROMPT_ITEMS.format(topic_a=topic_a, topic_b=topic_b, difficulty=difficulty)
            image = ctx.constraints.get("image") if isinstance(ctx.constraints, dict) else None
            if isinstance(image, dict) and image.get("description"):
                img_type = image.get("type") or "other"
                img_desc = str(image.get("description"))[:500]
                prompt = (
                    f"Image (type: {img_type}): {img_desc}\n"
                    "Use the image to construct the reasoning task. Reference 'the image' in the prompt.\n"
                ) + prompt
            for t in temps:
                resp = await call_gemini_json_async(prompt, system=SYSTEM_ITEMS, temperature=t)
                raw = (resp.get("items") or []) if isinstance(resp, dict) else []
                items = _coerce_items(raw)
                if items:
                    return items
            return []

        items_task = asyncio.create_task(_gen_items())
        plan_resp, items = await asyncio.gather(plan_task, items_task)
        # Emit plan
        plan = plan_resp.get("skill_plan") if isinstance(plan_resp, dict) else None
        if not plan:
            plan = [
                {"skill": "multi-step reasoning", "steps": ["identify", "compute", "check"]}
            ]
        await router.emit(EVENT_OUT_PLAN, {"ctx": ctx.to_dict(), "skill_plan": plan})
        # Emit items (may be empty in strict mode)
        image = ctx.constraints.get("image") if isinstance(ctx.constraints, dict) else None
        for it in items:
            it.difficulty = int(ctx.constraints.get("difficulty", 2)) if isinstance(ctx.constraints, dict) else 2
            if isinstance(image, dict) and image.get("description"):
                it.image_description = str(image.get("description"))[:500]
                it.image_type = str(image.get("type") or "other")
                it.uses_image = True
        await router.emit(EVENT_OUT_ITEMS, {"ctx": ctx.to_dict(), "items": [i.to_dict() for i in items]})

    router.subscribe(EVENT_IN, handle)