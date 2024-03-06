from fastapi import FastAPI, HTTPException
from typing import Callable, Optional

from basetypes import ExecuteInputRequest, ExecuteRequest, ExecuteResponse, StatusType
from events import EventsManager
from moon import build_lexer, build_parser, execute_program
from session import Session

import asyncio
import re


# Issue with loop already running
import nest_asyncio
nest_asyncio.apply()

api = FastAPI(
    title="Moon Interpreter API",
    version="0.1.0",
)

events = EventsManager()

class APISession(Session):
    def __init__(self, dummy: bool = False) -> None:
        super().__init__(dummy)
        if not dummy:
            self.output = ''

            self.input_listener_name = f"input-{self.code}"
            self.response_listener_name = f"reponse-{self.code}"

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

        execute_program(parsed_code, output_method, input_method)

        events.dispatch(self.response_listener_name, status="completed")
        self.remove()

    async def start(self, source_code: str) -> None:
        def output_method(*values: object) -> None:
            line = ' '.join([str(value) for value in values])
            self.output += f"{line}\n"

        def input_method(prompt: str) -> str:
            events.dispatch(self.response_listener_name, status="waiting", prompt=prompt)

            result_input = ''
            input_event = asyncio.Event()
            async def input_listener(input: str):
                nonlocal result_input
                result_input = input

                self.output += f"{prompt}{input}\n"

                events.remove_listener(input_listener, self.input_listener_name)
                input_event.set()

            events.add_listener(input_listener, self.input_listener_name)

            # Issue with loop already running
            loop = asyncio.get_event_loop()
            loop.run_until_complete(input_event.wait())

            return result_input

        asyncio.create_task(self.__execute(source_code, output_method, input_method))

@api.post("/execute")
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    """Executes the provided Moon code and returns the results of its execution."""
    session = APISession()

    result_status = "error"
    result_prompt = None

    response_event = asyncio.Event()
    async def response_listener(status: StatusType, prompt: Optional[str] = None) -> None:
        nonlocal result_status, result_prompt
        result_status = status
        result_prompt = prompt

        events.remove_listener(response_listener, session.response_listener_name)
        response_event.set()

    events.add_listener(response_listener, session.response_listener_name)

    asyncio.create_task(session.start(request.source_code))

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

        response_event = asyncio.Event()
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