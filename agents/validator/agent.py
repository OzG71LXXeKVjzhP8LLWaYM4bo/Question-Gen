from __future__ import annotations
from orchestrator.router import Router
from shared.schemas import JobContext

IN_TYPES = ["items.math", "items.english", "items.thinking"]
OUT = "items.validated"


def register(router: Router) -> None:
    async def validate(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        items = msg["items"]
        await router.emit(OUT, {"ctx": ctx.to_dict(), "items": items, "status": "pass"})

    for ev in IN_TYPES:
        router.subscribe(ev, validate)