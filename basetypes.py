from typing import Literal, Optional
from fastapi import Body
from pydantic import BaseModel

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