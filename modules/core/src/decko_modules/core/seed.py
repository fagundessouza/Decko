"""O registro do que o sistema criou sozinho, por empresa.

O núcleo guarda a identidade; quem cria a linha é o módulo dono da tabela, pelo serviço
dele. É esta divisão que permite a carga ser idempotente sem o núcleo conhecer o schema de
ninguém — ele sabe apenas que ``comercial.unidade.un`` resolve para uma linha de
``comercial_unidade``.

Módulo que semeia chama ``semear`` daqui. Pode: todo módulo declara ``core`` em
``depends``, então usar serviço do núcleo não cria dependência nova
(``docs/adr/0007-dependencia-entre-modulos.md``).

Decisão: ``docs/adr/0010-dado-semente-com-identidade-estavel.md``.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.core.models import SeedRecord, SeedStatus

# Nome de tabela válido no Postgres. Conferido porque ``table_name`` entra numa consulta
# por interpolação — não há como parametrizar identificador em SQL. O valor vem sempre do
# código de um módulo e nunca de requisição, e a conferência está aqui para que continue
# assim mesmo se alguém mudar o caminho.
_IDENTIFICADOR = re.compile(r"[a-z_][a-z0-9_]{0,62}")


class SeedError(RuntimeError):
    pass


def impressao(valores: Mapping[str, object]) -> str:
    """SHA-256 dos campos que a semente escreveu.

    Canônico pela ordenação das chaves, para a mesma semente dar sempre o mesmo hash. O
    que não é JSON vira texto: a semente é descritiva, e aqui não se guarda estrutura, se
    responde "mudou ou não".
    """
    bruto = json.dumps(dict(valores), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def intacta(registro: SeedRecord, valores_atuais: Mapping[str, object]) -> bool:
    """A linha semeada continua como a semente a deixou?

    É o que substitui o ``noupdate`` do Odoo. Lá o autor do módulo declara, antes de
    existir cliente, se o cliente vai querer editar aquele registro; aqui o sistema
    confere. Quem chama é o módulo, porque é ele que sabe quais campos ler.
    """
    return str(registro.fingerprint) == impressao(valores_atuais)


async def resolver(
    session: AsyncSession, *, tenant_id: uuid.UUID, module_name: str, ref: str
) -> SeedRecord | None:
    return await session.scalar(
        select(SeedRecord).where(
            SeedRecord.tenant_id == tenant_id,
            SeedRecord.module_name == module_name,
            SeedRecord.ref == ref,
        )
    )


async def _linha_existe(session: AsyncSession, table_name: str, row_id: uuid.UUID) -> bool:
    if not _IDENTIFICADOR.fullmatch(table_name):
        raise SeedError(f"'{table_name}' não é nome de tabela válido.")
    # O identificador foi conferido acima; o id vai parametrizado.
    consulta = text(f"SELECT 1 FROM {table_name} WHERE id = :row_id")  # noqa: S608
    encontrada = await session.scalar(consulta, {"row_id": row_id})
    return encontrada is not None


async def semear(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    module_name: str,
    ref: str,
    valores: Mapping[str, object],
    criar: Callable[[], Awaitable[tuple[str, uuid.UUID]]],
) -> bool:
    """Garante que aquela linha de semente exista, uma vez. Devolve True quando criou.

    ``criar`` é chamado no máximo uma vez na vida daquela empresa, e devolve a tabela e o
    id do que criou. Os três casos que não criam:

    - já registrado e a linha está lá → nada a fazer, e é o caso comum de reativar;
    - já registrado e a linha foi apagada pelo cliente → anota ``removido`` e **não
      recria**;
    - já marcado ``removido`` → continua não recriando, em qualquer reativação futura.
    """
    registro = await resolver(session, tenant_id=tenant_id, module_name=module_name, ref=ref)

    if registro is not None:
        if registro.status is SeedStatus.REMOVIDO:
            return False
        if await _linha_existe(session, registro.table_name, registro.row_id):
            return False
        # Existiu e não existe mais: foi o cliente. A decisão de não recriar fica gravada
        # para as próximas vezes não precisarem consultar a tabela de destino.
        registro.status = SeedStatus.REMOVIDO
        await session.flush()
        return False

    table_name, row_id = await criar()
    session.add(
        SeedRecord(
            tenant_id=tenant_id,
            module_name=module_name,
            ref=ref,
            table_name=table_name,
            row_id=row_id,
            fingerprint=impressao(valores),
            status=SeedStatus.ATIVO,
        )
    )
    await session.flush()
    return True
