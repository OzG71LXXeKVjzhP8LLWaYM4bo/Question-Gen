from __future__ import annotations
import uuid
from orchestrator.router import Router
from shared.schemas import JobContext, Item, Choice
from shared.gemini import call_gemini_json

EVENT_IN = "skill.plan"
EVENT_OUT = "items.english"

SYSTEM = (
    "You are a Year 6 Reading Comprehension item writer."
    " Create MCQs with 5 options (A-E) and a single correct answer."
    " Respond ONLY with JSON: {\"items\":[{prompt, choices:[{id,text}], answer, solution, tags}]}."
)

PROMPT = (
    "Write a short 3-4 sentence passage suitable for Year 6, then create 2 MCQs:"
    " one main-idea and one inference. Keep language simple. 5 options per item."
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


def register(router: Router) -> None:
    async def handle(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        resp = call_gemini_json(PROMPT, system=SYSTEM)
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
        await router.emit(EVENT_OUT, {"ctx": ctx.to_dict(), "items": [i.to_dict() for i in items]})

    router.subscribe(EVENT_IN, handle)