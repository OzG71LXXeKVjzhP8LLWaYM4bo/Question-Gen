from __future__ import annotations
import uuid
from orchestrator.router import Router
from shared.schemas import JobContext, Item, Choice
from shared.gemini import call_gemini_json_async
from shared.topics import MATH_TOPICS
import random

# Events
EVENT_IN_TOPIC = "topic.received"
EVENT_OUT_PLAN = "skill.plan.math"
EVENT_IN_PLAN_PRIMARY = "skill.plan.math"
EVENT_OUT_ITEMS = "items.math"

# System prompts
SYSTEM_PLAN = (
    "You design Year 6 Mathematical Reasoning item plans."
    " Return compact JSON with key skill_plan as a list of objects: {topic, skill, steps, distractors, difficulty}."
)

PROMPT_PLAN_TEMPLATE = (
    "Topic: {topic}\n"
    "Grade: Year 6\n"
    "Create a plan for 2 MCQs requiring 1–3 steps. Include common distractor strategies."
)

SYSTEM_ITEMS = (
    "You are a Year 6 Mathematical Reasoning item writer."
    " Produce multiple-choice questions (5 options: A-E) with a single correct answer and a short solution."
    " Respond ONLY with JSON: {\"items\": [ {prompt, choices:[{id,text}], answer, solution, tags} ] }."
)

PROMPT_ITEMS_BASE = (
    "Generate 1 Year 6 math MCQ that requires 1–3 steps."
    " Integrate both topics: {topic_a} and {topic_b}."
    " Use exact numeric answer, plausible distractors, and 5 options (A–E)."
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
                difficulty=int(it.get("difficulty", 2)) if isinstance(it, dict) else 2,
            )
        )
    return items


def _parse_plan(plan_resp: object, topic: str) -> list[dict]:
    if isinstance(plan_resp, list):
        return plan_resp
    if isinstance(plan_resp, dict):
        sp = plan_resp.get("skill_plan")
        if isinstance(sp, list):
            return sp
        return [plan_resp]
    return [
        {
            "topic": topic,
            "skill": "multi-step arithmetic",
            "steps": ["parse", "compute", "check"],
            "distractors": ["off-by-one", "wrong operation", "rounding"],
            "difficulty": "medium",
        }
    ]


def register(router: Router) -> None:
    # Planner: topic -> skill.plan.math
    async def handle_topic(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        topic = msg.get("topic", "mathematical reasoning")
        plan_resp = await call_gemini_json_async(PROMPT_PLAN_TEMPLATE.format(topic=topic), system=SYSTEM_PLAN)
        plan = _parse_plan(plan_resp, topic)
        await router.emit(EVENT_OUT_PLAN, {"ctx": ctx.to_dict(), "skill_plan": plan})

    router.subscribe(EVENT_IN_TOPIC, handle_topic)

    # Generator: skill.plan.math -> items.math
    async def handle_plan(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        plan = msg.get("skill_plan") or []
        plan_hint = ""
        if plan and isinstance(plan, list):
            p0 = plan[0]
            steps = ", ".join(p0.get("steps", [])[:4])
            dists = ", ".join(p0.get("distractors", [])[:4]) if isinstance(p0.get("distractors"), list) else ""
            topic = p0.get("topic") or p0.get("skill") or "Year 6 math"
            plan_hint = f"\nFocus topic: {topic}. Steps: {steps}. Distractors to include: {dists}."
        # Retry with temperature variations and 429 backoff
        import asyncio as _asyncio
        temps = [0.5, 0.8]
        backoff = 1.0
        items: list[Item] = []
        # choose two topics
        topic_a, topic_b = random.sample(MATH_TOPICS, 2)
        difficulty = int(ctx.constraints.get("difficulty", 2)) if isinstance(ctx.constraints, dict) else 2
        prompt = PROMPT_ITEMS_BASE.format(topic_a=topic_a, topic_b=topic_b, difficulty=difficulty) + plan_hint
        for t in temps:
            resp = await call_gemini_json_async(prompt, system=SYSTEM_ITEMS, temperature=t)
            err = resp.get("_error") if isinstance(resp, dict) else None
            if err and err.get("status") == 429:
                await _asyncio.sleep(backoff)
                backoff *= 2
                # retry same temperature once after backoff
                resp = await call_gemini_json_async(prompt, system=SYSTEM_ITEMS, temperature=t)
                err = resp.get("_error") if isinstance(resp, dict) else None
            raw_items = (resp.get("items") or []) if isinstance(resp, dict) else []
            items = _coerce_items(raw_items)
            if items:
                break
        # Ensure difficulty is set if model did not include it
        for it in items:
            if not getattr(it, "difficulty", None):
                it.difficulty = difficulty
        await router.emit(EVENT_OUT_ITEMS, {"ctx": ctx.to_dict(), "items": [i.to_dict() for i in items]})

    router.subscribe(EVENT_IN_PLAN_PRIMARY, handle_plan)