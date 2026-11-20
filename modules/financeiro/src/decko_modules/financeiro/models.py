"""O dinheiro, dos dois lados: onde ele entra e o que falta sair.

A conta responde **em qual destino caiu** — duas chaves Pix da mesma loja são dois
destinos, e era aí que a soma do fim do dia não fechava. A despesa responde **o que vence,
e quanto sai este mês** — a pergunta que a fazenda fez primeiro e que toda loja também faz.

Decisões: ``docs/adr/0014-conta-de-recebimento.md`` e ``docs/adr/0024-contas-a-pagar.md``.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


def _enum(tipo: type[StrEnum], nome: str) -> Enum:
    return Enum(tipo, name=nome, values_callable=lambda e: [m.value for m in e])


class StatusDespesa(StrEnum):
    """O mesmo conjunto de ``assinaturas.StatusCobranca``, e de propósito.

    É a mesma forma — algo devido, com vencimento, que vira pago ou não será pago. Inventar
    outro vocabulário para a mesma coisa faria quem lê o sistema aprender duas vezes.
    """

    ABERTA = "aberta"
    PAGA = "paga"
    # Conta que não será paga. Não é exclusão: fica, com o motivo.
    CANCELADA = "cancelada"


class Conta(TenantMixin, TimestampMixin, Base):
    """Um lugar de dinheiro: banco, chave Pix, ou a gaveta do caixa.

    Chamava-se ``ContaRecebimento`` enquanto só entrava dinheiro. A baixa da despesa sai da
    mesma conta em que a venda entra — a loja tem um Nubank PJ, não um de entrada e um de
    saída —, e o nome antigo passou a mentir. Ver ADR 0024, decisão 2.

    **Não é plano de contas.** Sem saldo, extrato, conciliação ou lançamento contábil — ver
    as decisões 5 e 6 do ADR 0014. Quanto entrou e quanto saiu é soma, e sai da consulta;
    saldo guardado precisaria de alguém mantendo verdadeiro.
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


class Despesa(TenantMixin, TimestampMixin, Base):
    """Uma conta a pagar: o que se deve, para quem, e quando vence.

    Linha gravada, e não dedução de um contrato: a conta de energia de março continua sendo
    a de março mesmo que a tarifa mude em abril — a mesma distinção do preço do item na
    venda (ADR 0008) e do valor da cobrança (ADR 0013).
    """

    __tablename__ = "financeiro_despesa"
    __table_args__ = (
        # A consulta que importa é "o que vence no período", e ela é sempre por empresa.
        Index("ix_financeiro_despesa_tenant_id_vencimento", "tenant_id", "vencimento"),
        Index("ix_financeiro_despesa_tenant_id_status", "tenant_id", "status"),
        CheckConstraint("valor >= 0", name="valor_nao_negativo"),
        CheckConstraint("valor_pago IS NULL OR valor_pago >= 0", name="valor_pago_nao_negativo"),
        # Paga tem data e valor; o que não está paga não tem nenhum dos dois. A regra vive
        # no serviço, mas também aqui: estado impossível não deve caber no banco.
        CheckConstraint(
            "(status = 'paga' AND pago_em IS NOT NULL AND valor_pago IS NOT NULL)"
            " OR (status <> 'paga' AND pago_em IS NULL AND valor_pago IS NULL)",
            name="paga_tem_data_e_valor",
        ),
    )

    id: Mapped[uuid.UUID] = primary_key()

    # Como quem paga chama: "Energia da sede", "Arrendamento", "Parcela do trator".
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)

    # Texto, e não cadastro — ADR 0024, decisão 3. A soma que interessa é por vencimento,
    # e nenhuma grafia de fornecedor atrapalha isso.
    fornecedor_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fornecedor_cpf_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)

    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[StatusDespesa] = mapped_column(
        _enum(StatusDespesa, "financeiro_status_despesa"),
        nullable=False,
        default=StatusDespesa.ABERTA,
    )

    # O que de fato saiu, que não é o que se devia: juros, multa, desconto por antecipação.
    # Tratar os dois como um só impediria a única conferência que interessa — "paguei mais
    # do que devia este mês, e em quê?". Ver ADR 0024, decisão 5.
    pago_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # De qual conta saiu. Opcional e RESTRICT, pelas decisões 3 e 4 do ADR 0014: quem não
    # separa contas não precisa escolher, e conta que já pagou algo não se apaga.
    conta_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financeiro_conta.id", ondelete="RESTRICT"),
        nullable=True,
    )

    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    conta: Mapped["Conta | None"] = relationship(lazy="joined")


TENANT_SCOPED_TABLES = (Conta.__tablename__, Despesa.__tablename__)
