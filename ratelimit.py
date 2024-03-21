import anyio
from fastapi import HTTPException

from functools import wraps
from typing import Callable, List

def rate_limit(max_calls: int, time_frame: float):
    def decorator(func: Callable):
        calls: List[float] = []

        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal calls
            now = anyio.current_time()
            calls = [
                call
                for call in calls
                if now - call <= time_frame
            ]

            if len(calls) >= max_calls:
                raise HTTPException(429, "Rate limit exceeded")

            calls.append(now)

            return await func(*args, **kwargs)

        return wrapper

    return decorator