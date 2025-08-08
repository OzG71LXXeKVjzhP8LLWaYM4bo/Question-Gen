import asyncio
from collections import defaultdict
from typing import Callable, Awaitable, Dict, List, Tuple

Handler = Callable[[dict], Awaitable[None]]


class Router:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._q: asyncio.Queue[Tuple[str, dict]] = asyncio.Queue()

    def subscribe(self, event: str, handler: Handler) -> None:
        self._subs[event].append(handler)

    async def emit(self, event: str, payload: dict) -> None:
        await self._q.put((event, payload))

    async def run(self) -> None:
        while True:
            event, payload = await self._q.get()
            for h in self._subs.get(event, []):
                asyncio.create_task(h(payload))