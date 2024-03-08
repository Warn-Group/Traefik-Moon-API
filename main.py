from fastapi import FastAPI, HTTPException
from anyio.abc import TaskGroup
from fastapi import HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from basetypes import API, ExecuteInputRequest, ExecuteRequest, ExecuteResponse, RawRequest, StatusType
from events import EventsManager
from service import ServiceSession

import anyio

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: API):
    async with anyio.create_task_group() as tg:
        app.task_group = tg
        app.events = EventsManager(tg)
        yield

router = APIRouter()

def app_factory():
    app = API(
        title="Moon Interpreter API",
        version="0.2.0",
        lifespan=lifespan
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://moon.warn.group"
        ],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(router)
    return app

@router.post("/execute")
async def execute(request: ExecuteRequest, raw_request: RawRequest) -> ExecuteResponse:
    """Executes the provided Moon code and returns the results of its execution."""
    session = ServiceSession(events=raw_request.app.events, timeout=5)
    events: EventsManager = raw_request.app.events
    task_group: TaskGroup = raw_request.app.task_group

    result_status = "error"
    result_prompt = None

    response_event = anyio.Event()
    async def response_listener(status: StatusType, prompt: Optional[str] = None) -> None:
        nonlocal result_status, result_prompt
        result_status = status
        result_prompt = prompt

        events.remove_listener(response_listener, session.response_listener_name)
        response_event.set()

    events.add_listener(response_listener, session.response_listener_name)

    task_group.start_soon(session.start, request.source_code)

    await response_event.wait()

    return ExecuteResponse(
        session_code=session.code,
        status=result_status,
        prompt=result_prompt,
        output=session.output,
    )

@router.post("/execute/input")
async def exexcute_input(request: ExecuteInputRequest, raw_request: RawRequest) -> ExecuteResponse:
    """Provides input to an ongoing Moon code execution identified by the session code."""
    dummy_session = ServiceSession(None, None, dummy=True) # type: ignore
    target_session = dummy_session.get_by_code(request.session_code)

    if target_session:
        events: EventsManager = raw_request.app.events

        result_status = "error"
        result_prompt = None

        response_event = anyio.Event()
        async def response_listener(status: StatusType, prompt: Optional[str] = None) -> None:
            nonlocal result_status, result_prompt
            result_status = status
            result_prompt = prompt

            events.remove_listener(response_listener, target_session.response_listener_name)
            response_event.set()

        events.add_listener(response_listener, target_session.response_listener_name)

        events.dispatch(target_session.input_listener_name, input=request.input)

        await response_event.wait()

        return ExecuteResponse(
            session_code=target_session.code,
            status=result_status,
            prompt=result_prompt,
            output=target_session.output,
        )

    raise HTTPException(400, "Invalid session code")