from events import EventsManager
from moon import build_lexer, build_parser, execute_program
from session import Session
from parallel import call_method, run_parallel

from typing import Callable

import anyio
import re

TIMEOUT_INPUT = 120
TIMEOUT_RUNNING = 10

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
            self.errors = []

            self.input_listener_name = f"input-{self.code}"
            self.response_listener_name = f"reponse-{self.code}"

            self.events = events
            self.timeout = timeout

    @classmethod
    def dummy_session(cls):
        """This dummy session is only meant to be used for accessing shared sessions without creating one."""
        return cls(None, dummy=True) # type: ignore

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

        if lexer.errors:
            self.errors.append(lexer.errors)

        if not parsed_code:
            raise ValueError("No instruction to execute")

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
        except Exception as exception:
            # match case unsupported in python 3.9

            try:
                raise exception

            except TimeoutError:
                self.errors.append("Program Timeout: code execution exceeded the allowed time limit")
            except ExceptionGroup:
                self.errors.append("Execution Error: an error occurred while running your code")
            except ValueError as e:
                self.errors.append(f"Invalid User Code: {' '.join(e.args)}")
            except Exception as e:
                self.errors.append(f"Unknown Error: An unexpected error occurred {type(e)}. Please report this issue on Github for further assistance: https://github.com/PaulMarisOUMary/Moon/issues")

            finally:
                self.remove()
                self.events.dispatch(self.response_listener_name, status="error")