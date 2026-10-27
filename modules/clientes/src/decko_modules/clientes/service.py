"""Cadastro de clientes, com a trilha que dado pessoal exige.

Toda alteração vira linha na trilha de auditoria. O que **não** vai para a trilha é o
valor do dado: registra-se que o CPF mudou, não qual CPF era e qual passou a ser. Copiar
dado pessoal para a trilha o espalharia para dentro de uma tabela que ninguém apaga, e
aí um pedido de exclusão passaria a ter dois lugares para alcançar.
"""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.clientes.models import Cliente
from decko_modules.core.models import AuditLog


class ClientesError(Exception):
    """Erro de regra do cadastro. Vira 422 na borda."""


async def registrar_na_trilha(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    acao: str,
    cliente: Cliente,
    campos: list[str] | None = None,
) -> None:
    """Grava o que foi feito, sem copiar o dado pessoal para dentro da trilha."""
    dados: dict[str, object] = {"nome": cliente.nome}
    if campos:
        dados["campos_alterados"] = sorted(campos)

    session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=acao,
            entity="cliente",
            entity_id=str(cliente.id),
            data=dados,
        )
    )


async def _documento_em_uso(
    session: AsyncSession, cpf_cnpj: str, *, exceto: uuid.UUID | None = None
) -> bool:
    consulta = select(Cliente.id).where(Cliente.cpf_cnpj == cpf_cnpj)
    if exceto is not None:
        consulta = consulta.where(Cliente.id != exceto)
    return await session.scalar(consulta) is not None


async def criar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    dados: dict[str, Any],
) -> Cliente:
    cpf_cnpj = dados.get("cpf_cnpj")
    if cpf_cnpj and await _documento_em_uso(session, cpf_cnpj):
        raise ClientesError("Já existe um cliente com este CPF ou CNPJ.")

    cliente = Cliente(tenant_id=tenant_id, **dados)
    session.add(cliente)
    await session.flush()

    await registrar_na_trilha(
        session, tenant_id=tenant_id, user_id=user_id, acao="cliente.create", cliente=cliente
    )
    return cliente


async def atualizar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    cliente: Cliente,
    dados: dict[str, Any],
) -> Cliente:
    cpf_cnpj = dados.get("cpf_cnpj")
    if cpf_cnpj and await _documento_em_uso(session, cpf_cnpj, exceto=cliente.id):
        raise ClientesError("Já existe outro cliente com este CPF ou CNPJ.")

    alterados = [campo for campo, valor in dados.items() if getattr(cliente, campo, None) != valor]
    for campo, valor in dados.items():
        setattr(cliente, campo, valor)
    await session.flush()

    if alterados:
        await registrar_na_trilha(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            acao="cliente.update",
            cliente=cliente,
            campos=alterados,
        )
    return cliente


async def definir_ativo(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    cliente: Cliente,
    ativo: bool,
) -> Cliente:
    """Tira ou devolve o cliente às telas de lançamento. Não apaga nada.

    Quem comprou aparece em venda, em nota e na trilha; apagar o cadastro deixaria esses
    documentos apontando para o vazio.
    """
    if cliente.ativo == ativo:
        return cliente

    cliente.ativo = ativo
    await session.flush()
    await registrar_na_trilha(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        acao="cliente.activate" if ativo else "cliente.deactivate",
        cliente=cliente,
    )
    return cliente


async def procurar(
    session: AsyncSession,
    *,
    busca: str | None = None,
    incluir_inativos: bool = False,
    limite: int = 100,
) -> list[Cliente]:
    """Acha por nome, apelido ou documento.

    O documento é comparado só por dígitos porque o vendedor digita com ponto e traço, e
    o banco guarda sem.
    """
    consulta = select(Cliente).order_by(Cliente.nome).limit(limite)
    if not incluir_inativos:
        consulta = consulta.where(Cliente.ativo)

    if busca:
        termo = busca.strip()
        digitos = "".join(caractere for caractere in termo if caractere.isdigit())
        criterios = [
            Cliente.nome.ilike(f"%{termo}%"),
            Cliente.apelido.ilike(f"%{termo}%"),
        ]
        if digitos:
            criterios.append(Cliente.cpf_cnpj.like(f"{digitos}%"))
        consulta = consulta.where(or_(*criterios))

    return list((await session.execute(consulta)).scalars().all())
