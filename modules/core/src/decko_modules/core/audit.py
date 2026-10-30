"""Escrita na trilha de auditoria.

A tabela existe desde a primeira migração e só o cadastro de empresa escrevia nela. Os
fluxos que mais interessam a uma investigação — quem entrou, quem tentou entrar, quem
contratou ou desligou módulo — não deixavam rastro.

## O que nunca entra

**O e-mail digitado numa tentativa de login.** Quando o endereço existe, `user_id` já diz
qual conta foi alvo, com precisão maior que um texto. Quando não existe, o que foi digitado
é palpite de quem sonda, e guardá-lo encheria a trilha de dado pessoal de terceiro sem
responder nada. Vale a regra 2 do ``CLAUDE.md``: a trilha registra **o que aconteceu**, não
uma cópia do que foi digitado.

Senha, token e hash também não entram, em nenhuma forma.

## O que não dá para registrar

Tentativa de login contra empresa **inexistente**. `audit_log.tenant_id` é obrigatório e a
tabela tem RLS: não há empresa a que prender a linha. Isso é consequência do isolamento,
não esquecimento — um registro de plataforma, fora da fronteira da empresa, é outra coisa
e precisaria da sua própria decisão.

## Por que há duas funções

Falha de autenticação termina em `HTTPException`, e a sessão da requisição desfaz tudo ao
levantar — inclusive a linha da trilha. Registro de falha vai em transação própria, que é
exatamente o caso em que a trilha precisa sobreviver.
"""

import ipaddress
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.core.models import AuditLog, User


def ip_de(request: Request) -> str | None:
    """O endereço de quem chamou, se for um IP de verdade.

    A coluna é ``INET``, e o cliente de teste se apresenta como ``testclient``: gravar sem
    conferir quebraria a requisição em vez de registrá-la. Atrás de proxy este valor é o
    do proxy — tratar ``X-Forwarded-For`` exige confiar no proxy, que é decisão de
    implantação e não existe ainda.
    """
    if request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


def registrar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    entity: str,
    user_id: uuid.UUID | None = None,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Acrescenta a linha na transação em curso.

    Para ação que deu certo: a trilha entra junto com o efeito, e as duas valem ou nenhuma.
    """
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            data=data,
            ip_address=ip,
        )
    )


async def registrar_a_parte(
    *,
    tenant_id: uuid.UUID,
    action: str,
    entity: str,
    user_id: uuid.UUID | None = None,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Acrescenta a linha em transação própria, que sobrevive ao desfazimento da requisição.

    É o caminho da **falha**: a requisição vai levantar, e com ela a trilha iria embora.
    """
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, tenant_id)
        registrar(
            session,
            tenant_id=tenant_id,
            action=action,
            entity=entity,
            user_id=user_id,
            entity_id=entity_id,
            data=data,
            ip=ip,
        )


# ---------------------------------------------------------------- leitura


@dataclass(frozen=True)
class Entrada:
    """Uma linha da trilha, com o nome de quem agiu já resolvido."""

    log: AuditLog
    autor: str | None


@dataclass(frozen=True)
class Pagina:
    total: int
    entradas: list[Entrada]


async def consultar(
    session: AsyncSession,
    *,
    action_prefix: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Pagina:
    """A trilha da empresa, do mais recente para o mais antigo.

    Devolve o total junto da página porque a tela precisa dizer quantas há: "50 de 3.412"
    é informação diferente de "50".

    O nome do autor vem por junção externa, e não por consulta por linha: a trilha cresce
    para sempre, e uma consulta por linha é a forma mais fácil de deixar esta tela lenta.
    Fica nulo quando a ação não teve autor — tentativa de entrada com e-mail que não
    existe — ou quando o usuário foi removido, porque a chave estrangeira é ``SET NULL``:
    a trilha sobrevive a quem a gerou, que é o ponto de ter trilha.
    """
    condicoes = []
    if action_prefix:
        # Agrupa por prefixo: "auth." é tudo de autenticação. Escapa o que o LIKE trata
        # como curinga, para um filtro digitado não virar uma varredura diferente.
        padrao = action_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condicoes.append(AuditLog.action.like(f"{padrao}%", escape="\\"))

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*condicoes))

    linhas = await session.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*condicoes)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return Pagina(
        total=total or 0,
        entradas=[Entrada(log=log, autor=autor) for log, autor in linhas],
    )
