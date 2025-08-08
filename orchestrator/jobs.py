from __future__ import annotations
import asyncio, uuid
from shared.schemas import JobContext
from orchestrator.router import Router


async def start_job(router: Router, topic: str) -> JobContext:
    ctx = JobContext.new()
    await router.emit("topic.received", {"ctx": ctx.to_dict(), "topic": topic})
    return ctx