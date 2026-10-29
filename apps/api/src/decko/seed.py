"""Porta de carga de dado-semente.

Terceira porta invertida do projeto, no mesmo padrão de ``decko/activation.py``: o host
declara, o módulo registra ao ser importado, e o host aplica sem conhecer o schema de
ninguém.

Aqui ela é obrigatória por um motivo que não é só de estilo. Semear é **escrever**, e
``docs/adr/0007-dependencia-entre-modulos.md`` proíbe módulo escrever na tabela de outro.
Sem a porta, contratar o perfil "comércio" faria o núcleo — ou pior, o arquivo de perfil —
gravar em ``comercial_unidade``. Com ela, quem escreve é sempre o dono da tabela, pelo
serviço dele, que é o único lugar onde ``fator`` e ``raiz_id`` saem certos.

Decisão e alternativas descartadas: ``docs/adr/0010-dado-semente-com-identidade-estavel.md``.
"""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

# Recebe a sessão e a empresa, e devolve os identificadores estáveis que criou nesta
# chamada. A lista vem vazia quando não havia nada para criar, que é o caso comum: a
# carga é idempotente, e repetir não cria nada.
SeedLoader = Callable[[AsyncSession, uuid.UUID], Awaitable[list[str]]]

_loaders: dict[str, SeedLoader] = {}


def register_seed_loader(module_name: str, loader: SeedLoader) -> None:
    """Registra o carregador de um módulo. Chamada pelo módulo ao ser importado."""
    _loaders[module_name] = loader


async def apply_seed(session: AsyncSession, *, module_name: str, tenant_id: uuid.UUID) -> list[str]:
    """Aplica a semente daquele módulo naquela empresa.

    Silencioso quando o módulo não tem carregador: a maioria não tem, e exigir que todos
    registrassem um vazio só criaria arquivo para não fazer nada.

    Chamada na ativação do módulo, e só nela — ver a decisão 3 do ADR 0010. Permissão
    precisa alcançar quem já usa o módulo, porque senão a tela nova abre em "permissão
    necessária"; semente é dado do cliente, e entrar no catálogo de quem já opera numa
    subida de aplicação que ninguém pediu é intrusão.
    """
    loader = _loaders.get(module_name)
    if loader is None:
        return []
    return await loader(session, tenant_id)
