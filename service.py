from events import EventsManager
from moon import build_lexer, build_parser, execute_program
from session import Session
from parallel import call_method, run_parallel

from typing import Callable

import anyio
import re

TIMEOUT_INPUT = 30
TIMEOUT_RUNNING = 2.5

def blocking_execute(sock, parsed_code):
    """This function need to be in the global scope"""
    with sock.makefile("rb") as f:
        def input_method(prompt: str):
            return call_method(sock, f, "input_method", prompt)
            
        def output_method(*values: object):
            return call_method(sock, f, "output_method", *values)

        execute_program(parsed_code, input_method=input_method, output_method=output_method)
        call_method(sock, f, "break")

class ServiceSession(Session):
    def __init__(self, events: EventsManager, timeout: float = TIMEOUT_RUNNING, dummy: bool = False) -> None:
        super().__init__(dummy)
        if not dummy:
            self.output = ''

            self.input_listener_name = f"input-{self.code}"
            self.response_listener_name = f"reponse-{self.code}"

            self.events = events
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

        self.events.dispatch(self.response_listener_name, status="completed")
        self.remove()

    async def start(self, source_code: str) -> None:
        async def output_method(*values: object) -> None:
            line = ' '.join([str(value) for value in values])
            self.output += f"{line}\n"

        async def input_method(prompt: str) -> str:
            self.cancel_scope.deadline = anyio.current_time() + TIMEOUT_INPUT
            self.events.dispatch(self.response_listener_name, status="waiting", prompt=prompt)

            result_input = ''
            input_event = anyio.Event()
            async def input_listener(input: str):
                nonlocal result_input
                result_input = input

                self.output += f"{prompt}{input}\n"

                self.events.remove_listener(input_listener, self.input_listener_name)
                input_event.set()

            self.events.add_listener(input_listener, self.input_listener_name)

            await input_event.wait()

            self.cancel_scope.deadline = anyio.current_time() + TIMEOUT_RUNNING

            return result_input

        try:
            with anyio.fail_after(self.timeout) as cancel_scope:
                self.cancel_scope = cancel_scope
                await self.__execute(source_code, output_method, input_method)
        except TimeoutError:
            self.remove()
            self.events.dispatch(self.response_listener_name, status="error")