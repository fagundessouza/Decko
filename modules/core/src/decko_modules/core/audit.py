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
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.core.models import AuditLog


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
