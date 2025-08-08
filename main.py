import asyncio
from orchestrator.router import Router
from orchestrator.jobs import start_job
from agents.thinking.agent import register as reg_thinking
from agents.math.agent import register as reg_math
from agents.english.agent import register as reg_english
from agents.validator.agent import register as reg_validator
from shared.storage import save_items, ensure_question_dirs


async def main() -> None:
    router = Router()
    # Register agents
    reg_thinking(router)
    reg_math(router)
    reg_english(router)
    reg_validator(router)

    # Ensure directories
    ensure_question_dirs()

    # Track validated emissions and stop after three (math + english + thinking stubs)
    validated_count = 0
    stop_event = asyncio.Event()

    async def sink(msg: dict) -> None:
        nonlocal validated_count
        validated_count += 1
        print(f"VALIDATED: {len(msg['items'])} items")
        paths = save_items(msg["ctx"], msg["items"])  # write per subject
        for p in paths:
            print(f"saved: {p}")
        if validated_count >= 3:
            stop_event.set()

    router.subscribe("items.validated", sink)

    # Start router in background
    loop_task = asyncio.create_task(router.run())

    # Kick off a job
    await start_job(router, topic="Year 6 selective practice")

    # Wait until we have all validated emissions, then stop
    await stop_event.wait()
    loop_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await loop_task


if __name__ == "__main__":
    import contextlib
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass