from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Callable, Optional

from basetypes import ExecuteInputRequest, ExecuteRequest, ExecuteResponse, StatusType
from events import EventsManager
from moon import build_lexer, build_parser, execute_program
from session import Session
from parallel import call_method, run_parallel

import anyio
import re

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    async with anyio.create_task_group() as tg:
        app.task_group = tg
        app.events = EventsManager(tg)
        yield

class API(FastAPI):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task_group: TaskGroup
        self.events: EventsManager

api = API(
    title="Moon Interpreter API",
    version="0.1.0",
    lifespan=lifespan,
)

origins = [
    "http://localhost:3000",
    "https://moon.warn.group"
]

api.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def blocking_execute(sock, parsed_code):
    """This function need to be in the global scope"""
    with sock.makefile("rb") as f:
        def input_method(prompt: str):
            return call_method(sock, f, "input_method", prompt)
            
        def output_method(*values: object):
            return call_method(sock, f, "output_method", *values)

        execute_program(parsed_code, input_method=input_method, output_method=output_method)
        call_method(sock, f, "break")

class APISession(Session):
    def __init__(self, dummy: bool = False, timeout: int = 10) -> None:
        super().__init__(dummy)
        if not dummy:
            self.output = ''

            self.input_listener_name = f"input-{self.code}"
            self.response_listener_name = f"reponse-{self.code}"

            self.timeout = timeout

    async def __execute(self, source_code: str, output_method: Callable, input_method: Callable) -> None:
        source_code = source_code.lstrip('\n')
        source_code = re.sub(
            pattern=r"^(\s{4})+",
            repl=lambda m: '\t' * (len(m.group(0)) // 4),
            string=source_code,
            flags=re.MULTILINE
        )

        lexer = build_lexer()
        lexer.input(source_code)
        parser = build_parser()
        parsed_code = parser.parse(source_code+'\n', lexer=lexer)

        methods = {
            "input_method": input_method, "output_method": output_method
        }

        await run_parallel(methods, blocking_execute, parsed_code)

        api.events.dispatch(self.response_listener_name, status="completed")
        self.remove()

    async def start(self, source_code: str) -> None:
        async def output_method(*values: object) -> None:
            line = ' '.join([str(value) for value in values])
            self.output += f"{line}\n"

        async def input_method(prompt: str) -> str:
            self.cancel_scope.deadline = anyio.current_time() + 5
            api.events.dispatch(self.response_listener_name, status="waiting", prompt=prompt)

            result_input = ''
            input_event = anyio.Event()
            async def input_listener(input: str):
                nonlocal result_input
                result_input = input

                self.output += f"{prompt}{input}\n"

                api.events.remove_listener(input_listener, self.input_listener_name)
                input_event.set()

            api.events.add_listener(input_listener, self.input_listener_name)

            await input_event.wait()

            return result_input

        try:
            with anyio.fail_after(self.timeout) as cancel_scope:
                self.cancel_scope = cancel_scope
                await self.__execute(source_code, output_method, input_method)
        except TimeoutError:
            self.remove()
            api.events.dispatch(self.response_listener_name, status="error")

@api.post("/execute")
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    """Executes the provided Moon code and returns the results of its execution."""
    session = APISession(timeout=5)

    result_status = "error"
    result_prompt = None

    response_event = anyio.Event()
    async def response_listener(status: StatusType, prompt: Optional[str] = None) -> None:
        nonlocal result_status, result_prompt
        result_status = status
        result_prompt = prompt

        api.events.remove_listener(response_listener, session.response_listener_name)
        response_event.set()

    api.events.add_listener(response_listener, session.response_listener_name)

    api.task_group.start_soon(session.start, request.source_code)

    await response_event.wait()

    return ExecuteResponse(
        session_code=session.code,
        status=result_status,
        prompt=result_prompt,
        output=session.output,
    )

@api.post("/execute/input")
async def exexcute_input(request: ExecuteInputRequest) -> ExecuteResponse:
    """Provides input to an ongoing Moon code execution identified by the session code."""
    dummy_session = APISession(dummy=True)
    target_session = dummy_session.get_by_code(request.session_code)

    if target_session:
        result_status = "error"
        result_prompt = None

        response_event = anyio.Event()
        async def response_listener(status: StatusType, prompt: Optional[str] = None) -> None:
            nonlocal result_status, result_prompt
            result_status = status
            result_prompt = prompt

            api.events.remove_listener(response_listener, target_session.response_listener_name)
            response_event.set()

        api.events.add_listener(response_listener, target_session.response_listener_name)

        api.events.dispatch(target_session.input_listener_name, input=request.input)

        await response_event.wait()

        return ExecuteResponse(
            session_code=target_session.code,
            status=result_status,
            prompt=result_prompt,
            output=target_session.output,
        )

    raise HTTPException(400, "Invalid session code")