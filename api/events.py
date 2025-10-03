import asyncio
import functools

from anyio.abc import TaskGroup
from typing import Any, Callable, Dict, List, Literal


class SingletonMeta(type):
    _instances: Dict[type, object] = {}

    def __call__(cls, *args, **kwargs) -> object:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class _MissingSentinel(metaclass=SingletonMeta):
    __slots__ = ()

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, _MissingSentinel)

    def __bool__(self) -> bool:
        return False

    def __hash__(self) -> int:
        return 0

    def __repr__(self) -> Literal["..."]:
        return "..."

MISSING: Any = _MissingSentinel()

class EventsManager():
    def __init__(self, task_group: TaskGroup) -> None:
        self._listeners: Dict[str, List[Callable]] = {}
        self._task_group = task_group

    def remove_listener(self, func: Callable, name: str = MISSING) -> None:
        name = func.__name__ if name is MISSING else name

        if name not in self._listeners:
            raise ValueError(f"Listener '{name}' not found.")

        self._listeners[name].remove(func)
        if not self._listeners[name]:
            del self._listeners[name]

    def add_listener(self, func: Callable, name: str = MISSING) -> None:
        name = func.__name__ if name is MISSING else name

        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Listeners must be coroutines.")

        if name in self._listeners:
            self._listeners[name].append(func)
        else:
            self._listeners[name] = [func]

    def listen(self, name: str = MISSING) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.add_listener(func, name)
            return func

        return decorator

    def dispatch(self, event: str, *args, **kwargs) -> None:
        listener = self._listeners.get(event, None)
        if listener:
            for func in listener:
                self._task_group.start_soon(functools.partial(func, *args, **kwargs))