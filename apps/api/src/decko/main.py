from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from decko.config import get_settings
from decko.db import check_connection, engine
from decko.modules import ModuleManifest, load_into

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Decko API",
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    loaded: list[ModuleManifest] = load_into(app, settings.modules_dir)
    app.state.modules = loaded

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, Any]:
        database = await check_connection()
        return {
            "status": "ok",
            "env": settings.env,
            "database": {
                "user": database["user"],
                # Se o papel da aplicação ignorar RLS, o isolamento entre empresas não
                # existe. Isso é exposto para ser verificável, não presumido.
                "bypasses_rls": database["bypasses_rls"],
            },
            "modules": [{"name": m.name, "version": m.version, "label": m.label} for m in loaded],
        }

    return app


app = create_app()
