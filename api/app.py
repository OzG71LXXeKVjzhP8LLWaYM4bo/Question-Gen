from __future__ import annotations
import asyncio
from typing import Literal, Optional, Dict, List
from fastapi import FastAPI
from pydantic import BaseModel
from orchestrator.router import Router
from orchestrator.jobs import start_job
from agents.thinking.agent import register as reg_thinking
from agents.math.agent import register as reg_math
from agents.english.agent import register as reg_english
from agents.validator.agent import register as reg_validator
import contextlib
import random
from shared.topics import MATH_TOPICS, THINKING_TOPICS, ENGLISH_TOPICS

app = FastAPI(title="Question-Gen API", version="0.1.0")


class GenerateRequest(BaseModel):
    subject: Literal["thinking", "math", "english"]


class GenerateResponse(BaseModel):
    items: List[dict]
    failed: List[dict]


def _pick_seed_topic_for_subject(subject: str) -> str:
    pool: List[str]
    if subject == "math":
        pool = MATH_TOPICS
    elif subject == "thinking":
        pool = THINKING_TOPICS
    else:
        pool = ENGLISH_TOPICS
    sample = random.sample(pool, k=min(2, len(pool)))
    return " and ".join(sample)


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    router = Router()
    # Register only the requested subject
    if req.subject == "thinking":
        reg_thinking(router)
    elif req.subject == "math":
        reg_math(router)
    else:
        reg_english(router)
    reg_validator(router)

    items: List[dict] = []
    failures: List[dict] = []
    done = asyncio.Event()

    async def sink(msg: dict) -> None:
        nonlocal items, failures
        items.extend(msg.get("items", []))
        failures.extend(msg.get("failed", []))
        done.set()

    router.subscribe("items.validated", sink)

    # Run router and job
    loop_task = asyncio.create_task(router.run())
    seed_topic = _pick_seed_topic_for_subject(req.subject)
    await start_job(router, topic=seed_topic)

    # Timeout guard: 30s
    try:
        await asyncio.wait_for(done.wait(), timeout=30)
    except asyncio.TimeoutError:
        pass
    finally:
        loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await loop_task

    return GenerateResponse(items=items, failed=failures) 