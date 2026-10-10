import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any


def run_async(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Run an async integration exercise with a Psycopg-compatible Windows loop."""
    if sys.platform == "win32":
        return asyncio.run(
            coroutine,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coroutine)
