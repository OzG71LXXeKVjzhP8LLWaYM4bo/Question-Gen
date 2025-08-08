from __future__ import annotations
import uuid
from orchestrator.router import Router
from shared.schemas import JobContext, Item, Choice
from shared.gemini import call_gemini_json

# Events
EVENT_IN_TOPIC = "topic.received"
EVENT_OUT_PLAN = "skill.plan.english"
EVENT_IN_PLAN_PRIMARY = "skill.plan.english"
EVENT_OUT_ITEMS = "items.english"

SYSTEM_PLAN = (
    "You design Year 6 Reading Comprehension item plans."
    " Return JSON key skill_plan as a list of objects: {passage_type, focus, steps, difficulty}."
)

PROMPT_PLAN_TEMPLATE = (
    "Topic: {topic}\n"
    "Grade: Year 6\n"
    "Create a plan for 2 MCQs (main idea, inference). Keep reading level Lexile 800–1000."
)

SYSTEM_ITEMS = (
    "You are a Year 6 Reading Comprehension item writer."
    " Create MCQs with 5 options (A-E) and a single correct answer."
    " Respond ONLY with JSON: {\"items\":[{prompt, choices:[{id,text}], answer, solution, tags}]}."
)

PROMPT_ITEMS_BASE = (
    "Write a short 3-4 sentence passage (Year 6). Then create 2 MCQs: main idea and inference."
    " Keep language simple. 5 options per item."
)


def _coerce_items(raw_items: list[dict]) -> list[Item]:
    items: list[Item] = []
    labels = ["A", "B", "C", "D", "E"]
    for it in raw_items[:5]:
        prompt = it.get("prompt") or ""
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
                subject="english",
                prompt=prompt,
                choices=labeled,
                answer=it.get("answer", "A"),
                solution=it.get("solution", ""),
                tags=it.get("tags", ["Year6", "reading"]),
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
            "passage_type": "informational",
            "focus": "main idea + inference",
            "steps": ["read", "summarise", "infer from clues"],
            "difficulty": "medium",
        }
    ]


def register(router: Router) -> None:
    # Planner: topic -> skill.plan.english
    async def handle_topic(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        topic = msg.get("topic", "reading")
        plan_resp = call_gemini_json(PROMPT_PLAN_TEMPLATE.format(topic=topic), system=SYSTEM_PLAN)
        plan = _parse_plan(plan_resp, topic)
        await router.emit(EVENT_OUT_PLAN, {"ctx": ctx.to_dict(), "skill_plan": plan})

    router.subscribe(EVENT_IN_TOPIC, handle_topic)

    # Generator: skill.plan.english -> items.english
    async def handle_plan(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        plan = msg.get("skill_plan") or []
        plan_hint = ""
        if plan and isinstance(plan, list):
            p0 = plan[0]
            focus = p0.get("focus") or "main idea and inference"
            ptype = p0.get("passage_type") or "informational"
            plan_hint = f"\nPassage type: {ptype}. Focus: {focus}."
        resp = call_gemini_json(PROMPT_ITEMS_BASE + plan_hint, system=SYSTEM_ITEMS)
        raw_items = resp.get("items") or []
        items = _coerce_items(raw_items) or [
            Item(
                id=str(uuid.uuid4()),
                subject="english",
                prompt="What is the main idea of the short passage?",
                choices=[
                    Choice(id="A", text="Detail unrelated to main point"),
                    Choice(id="B", text="Correct main idea"),
                    Choice(id="C", text="Minor detail"),
                    Choice(id="D", text="Author background"),
                    Choice(id="E", text="Opinion not stated"),
                ],
                answer="B",
                solution="The passage primarily argues for the main point stated in option B.",
                tags=["main-idea", "Year6"],
            )
        ]
        await router.emit(EVENT_OUT_ITEMS, {"ctx": ctx.to_dict(), "items": [i.to_dict() for i in items]})

    router.subscribe(EVENT_IN_PLAN_PRIMARY, handle_plan)