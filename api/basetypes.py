from anyio.abc import TaskGroup
from fastapi import FastAPI, Request
from pydantic import BaseModel, StringConstraints
from typing import Annotated, Any, Literal, Optional

from events import EventsManager

# API and Router

class API(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events: EventsManager
        self.task_group: TaskGroup

# Requests and Responses
class ExecuteRequest(BaseModel):
    source_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=0, max_length=500_000)]

StatusType = Literal["completed", "waiting", "error"]

class ExecuteResponse(BaseModel):
    session_code: str
    status: StatusType
    prompt: Optional[str] = None # if status == "waiting"
    output: str
    errors: list[Any]

class ExecuteInputRequest(BaseModel):
    session_code: Annotated[str, StringConstraints(min_length=32, max_length=32, pattern=r"^[0-9a-fA-F]{32}$")]
    input: Annotated[str, StringConstraints(min_length=0, max_length=5_000)]

class RawRequest(Request):
    @property
    def app(self) -> API:
        return super().app