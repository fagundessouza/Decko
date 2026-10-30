"""Conta de recebimento: para onde o dinheiro foi.

O ponto de venda já diz **como** o cliente pagou. Esta tabela responde a outra pergunta,
que é a que não fecha no fim do dia: **em qual conta caiu**. Duas chaves Pix da mesma loja
são dois destinos diferentes.

Decisões e o que ficou de fora de propósito: ``docs/adr/0014-conta-de-recebimento.md``.
"""

import uuid

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class ContaRecebimento(TenantMixin, TimestampMixin, Base):
    """Um destino de dinheiro: banco, chave Pix, ou a gaveta do caixa.

    **Não é plano de contas.** Sem saldo, extrato, conciliação ou lançamento contábil — ver
    as decisões 5 e 6 do ADR 0014. Quanto entrou em cada conta é soma dos pagamentos, e sai
    da consulta; saldo guardado precisaria de alguém mantendo verdadeiro.
    """

    __tablename__ = "financeiro_conta"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nome", name="uq_financeiro_conta_tenant_id_nome"),
        Index("ix_financeiro_conta_tenant_id_ativa", "tenant_id", "ativa"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    # Como quem opera chama: "Nubank PJ", "Cofre", "Maquininha Stone".
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    instituicao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Texto, e não um tipo: chave Pix é CPF, CNPJ, e-mail, telefone ou aleatória.
    chave_pix: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Conta não se apaga, desativa — igual ao cadastro de clientes, e pela mesma razão: o
    # pagamento de ontem continua apontando para ela.
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


TENANT_SCOPED_TABLES = (ContaRecebimento.__tablename__,)
