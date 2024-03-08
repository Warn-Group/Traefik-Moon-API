from anyio.abc import TaskGroup
from fastapi import Body, FastAPI, Request
from pydantic import BaseModel
from typing import Literal, Optional

from events import EventsManager

# API and Router

class API(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events: EventsManager
        self.task_group: TaskGroup

# Requests and Responses
class ExecuteRequest(BaseModel):
    source_code: str = Body(...)

StatusType = Literal["completed", "waiting", "error"]

class ExecuteResponse(BaseModel):
    session_code: str
    status: StatusType
    prompt: Optional[str] = None
    output: Optional[str] = None
    errors: Optional[str] = None

class ExecuteInputRequest(BaseModel):
    session_code: str
    input: str = Body(...)

class RawRequest(Request):
    @property
    def app(self) -> API:
        return super().app