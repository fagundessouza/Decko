from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from decko.activation import reconcile_permissions
from decko.config import get_settings
from decko.db import check_connection, engine
from decko.modules import ModuleManifest, load_into
from decko.profiles import discover as discover_profiles

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Módulo evolui: a versão nova declara permissão que a anterior não tinha, e quem já
    # usava o módulo não a receberia por caminho nenhum. Acertar aqui é o que faz uma
    # atualização chegar às empresas que já existem.
    await reconcile_permissions(
        {manifest.name: manifest.permissions for manifest in app.state.modules}
    )
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

    # Front servido de outro domínio — a tela na Vercel, a API num túnel ou num VPS — faz
    # requisição entre origens, e o navegador recusa sem isto. Quando os dois estão atrás
    # do mesmo domínio a lista fica vazia e o middleware nem entra.
    #
    # `allow_credentials` fica **falso** de propósito: a sessão do Decko viaja no cabeçalho
    # `Authorization`, não em cookie, e permitir credencial sem precisar afrouxa o que o
    # navegador protege de graça.
    origens = settings.allowed_origins
    if origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origens,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    loaded: list[ModuleManifest] = load_into(app, settings.modules_dir)
    app.state.modules = loaded

    # Perfis são conferidos contra os módulos instalados na leitura: um perfil que liste
    # módulo inexistente derruba a inicialização, em vez de falhar na contratação.
    app.state.profiles = discover_profiles(
        settings.profiles_dir, {manifest.name: manifest for manifest in loaded}
    )

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
