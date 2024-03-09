import anyio.abc
import anyio.to_process
import pickle
import functools
import socket

from typing import Any, Callable
from anyio.streams.buffered import BufferedByteReceiveStream

async def accept(ml):
    sockets = []

    async def do_accept(listener):
        sockets.append(await listener.accept())
        tg.cancel_scope.cancel()

    async with anyio.create_task_group() as tg:
        for l in ml.listeners:
            tg.start_soon(do_accept, l)

    result, *rest = sockets
    for s in rest:
        await s.aclose()

    return result

def run_in_process(addr, func, *args):
    with socket.create_connection(addr) as sock:
        func(sock, *args)

async def listen_to_process(func, *args, task_status):
    async with anyio.create_task_group() as tg:
        host = "::1"
        async with await anyio.create_tcp_listener(local_host=host) as ml:
            local_port = ml.extra_attributes[anyio.abc.SocketAttribute.local_port]()
            tg.start_soon(
                functools.partial(
                    anyio.to_process.run_sync,
                    run_in_process,
                    (host, local_port),
                    func,
                    *args,
                    cancellable=True,
                )
            )
            task_status.started(await accept(ml))
            await ml.aclose()

def call_method(sock, f, method_name, *args, **kwargs):
    dump = pickle.dumps((method_name, args, kwargs))
    sock.sendall(f"{len(dump)}\n".encode())
    sock.sendall(dump)
    length = int(f.readline().decode())
    return pickle.loads(f.read(length))

async def send_msg(socket, msg):
    dump = pickle.dumps(msg)
    await socket.send(f"{len(dump)}\n".encode())
    await socket.send(dump)

async def run_parallel(callbacks: dict[str, Callable], method: Callable, /, *args: Any):
    async with anyio.create_task_group() as tg:
            async with await tg.start(
                listen_to_process, method, *args
            ) as socket:
                buffer = BufferedByteReceiveStream(socket)
                while True:
                    length = int((await buffer.receive_until(b"\n", 50)).decode())
                    method_name, args, kwargs = pickle.loads(await buffer.receive_exactly(length))
                    if method_name == "break":
                        await send_msg(socket, None)
                        break

                    result = await callbacks[method_name](*args, **kwargs)
                    await send_msg(socket, result)