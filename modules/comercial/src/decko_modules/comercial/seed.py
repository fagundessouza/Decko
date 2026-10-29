"""A semente da base comercial: as unidades raiz.

Uma empresa que contrata "Comércio em geral" caía numa tela de unidades vazia e tinha de
inventar o sistema de medidas antes de cadastrar o primeiro produto. Isto resolve essa
tela, e só ela.

**O que não está aqui, e por quê.** "Caixa com 12" e "fardo com 10 caixas" parecem semente
óbvia e são suposição: o fator muda por produto e por fornecedor, e errado ele contamina
todo cálculo de saldo. Categoria por segmento tem o mesmo defeito — as categorias de um
supermercado saem do discovery, não de dedução. Regra 6 do ``CLAUDE.md``.

Unidade, quilograma e litro não são suposição: são as raízes dos três sistemas de medida
que qualquer loja usa, e cada uma tem fator 1 por definição.

Decisão: ``docs/adr/0010-dado-semente-com-identidade-estavel.md``.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.seed import register_seed_loader
from decko_modules.comercial import service
from decko_modules.comercial.models import Unidade
from decko_modules.core import seed as registro

MODULO = "comercial"

# (sufixo do ref, nome, símbolo). O ref é o identificador estável e não muda nunca; o nome
# é o que aparece na tela e o cliente pode renomear à vontade, porque quem reconhece a
# semente é o ref.
UNIDADES_RAIZ = (
    ("un", "Unidade", "UN"),
    ("kg", "Quilograma", "KG"),
    ("l", "Litro", "L"),
)


async def _por_nome(session: AsyncSession, tenant_id: uuid.UUID, nome: str) -> Unidade | None:
    return await session.scalar(
        select(Unidade).where(Unidade.tenant_id == tenant_id, Unidade.nome == nome)
    )


async def carregar(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    criados: list[str] = []

    for sufixo, nome, simbolo in UNIDADES_RAIZ:
        # A empresa que já criou "Unidade" à mão fica com a dela. O nome é único por
        # empresa, então sem esta conferência a carga quebraria na restrição — e adotar a
        # linha do cliente como semente seria pior: ela não é nossa para atualizar depois.
        if await _por_nome(session, tenant_id, nome) is not None:
            continue

        async def criar(nome: str = nome, simbolo: str = simbolo) -> tuple[str, uuid.UUID]:
            # Pelo serviço, nunca por INSERT: é ele que resolve `fator` e `raiz_id`. Uma
            # raiz inserida à mão com raiz_id errado converte errado em silêncio.
            unidade = await service.criar_unidade(
                session, tenant_id=tenant_id, nome=nome, simbolo=simbolo
            )
            return Unidade.__tablename__, unidade.id

        ref = f"{MODULO}.unidade.{sufixo}"
        if await registro.semear(
            session,
            tenant_id=tenant_id,
            module_name=MODULO,
            ref=ref,
            valores={"nome": nome, "simbolo": simbolo},
            criar=criar,
        ):
            criados.append(ref)

    return criados


register_seed_loader(MODULO, carregar)
