from anyio import create_task_group
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from basetypes import API
from events import EventsManager
from routes import router


@asynccontextmanager
async def lifespan(app: API):
    async with create_task_group() as tg:
        app.task_group = tg
        app.events = EventsManager(tg)
        yield


def app_factory():
    app = API(title="Moon Interpreter API", version="0.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://moon.warn.group",
            "https://moon-playground.vercel.app",
        ],
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(router)
    return app
