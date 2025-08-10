from __future__ import annotations
from typing import Optional, Dict
from shared.schemas import JobContext
from orchestrator.router import Router


async def start_job(router: Router, topic: str, constraints: Optional[Dict] = None) -> JobContext:
    ctx = JobContext.new()
    if constraints:
        ctx.constraints.update(constraints)
    await router.emit("topic.received", {"ctx": ctx.to_dict(), "topic": topic})
    return ctx