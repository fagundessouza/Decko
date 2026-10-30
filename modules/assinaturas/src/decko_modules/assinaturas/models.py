"""Assinatura recorrente: plano, assinante e a cobrança de cada mês.

Decisões e o que ficou de fora de propósito: ``docs/adr/0013-assinatura-recorrente.md``.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key

# Dias entre o vencimento e o bloqueio. Contados do **vencimento**, não do aviso: aviso que
# não chega — e-mail no spam, celular trocado — não pode adiar o relógio para sempre.
DIAS_DE_AVISO = 5


class StatusAssinatura(StrEnum):
    ATIVA = "ativa"
    # Encerrada por quem vende ou por quem assina. Não some: as cobranças dela continuam.
    CANCELADA = "cancelada"


class StatusCobranca(StrEnum):
    ABERTA = "aberta"
    PAGA = "paga"
    # Cobrança que não será recebida. Não é exclusão: fica, com o motivo.
    CANCELADA = "cancelada"


class Acesso(StrEnum):
    """O que a assinatura permite **hoje**.

    Não é coluna: é função da cobrança mais antiga em aberto e da data — ver a decisão 3 do
    ADR 0013. Guardar exigiria alguém passando para atualizar, e entre duas passadas estaria
    errado: bloqueando quem pagou ontem, liberando quem venceu hoje.
    """

    EM_DIA = "em_dia"
    EM_AVISO = "em_aviso"
    BLOQUEADA = "bloqueada"


def _enum(python_enum: type, name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Plano(TenantMixin, TimestampMixin, Base):
    """O que se vende, e por quanto."""

    __tablename__ = "assinaturas_plano"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nome", name="uq_assinaturas_plano_tenant_id_nome"),
        CheckConstraint("preco_mensal >= 0", name="preco_mensal_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(400), nullable=True)
    preco_mensal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Plano aposentado não é apagado: assinatura antiga continua apontando para ele.
    ativo: Mapped[bool] = mapped_column(nullable=False, default=True)


class Assinatura(TenantMixin, TimestampMixin, Base):
    """Quem assina o quê, e em que dia vence."""

    __tablename__ = "assinaturas_assinatura"
    __table_args__ = (
        Index("ix_assinaturas_assinatura_tenant_id_status", "tenant_id", "status"),
        CheckConstraint(
            "dia_vencimento BETWEEN 1 AND 28", name="dia_vencimento_existe_em_todo_mes"
        ),
    )

    id: Mapped[uuid.UUID] = primary_key()
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        # RESTRICT como na venda: o cadastro de clientes nunca apaga, só desativa, para a
        # cobrança continuar apontando para alguém.
        ForeignKey("clientes_cliente.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plano_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assinaturas_plano.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[StatusAssinatura] = mapped_column(
        _enum(StatusAssinatura, "assinaturas_status_assinatura"),
        nullable=False,
        default=StatusAssinatura.ATIVA,
    )

    inicio: Mapped[date] = mapped_column(Date, nullable=False)
    # Até 28 para existir em fevereiro. Quem vende no dia 31 descobre o problema em março.
    dia_vencimento: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sem relacionamento para `Plano` de propósito. Objeto recém-criado não tem relação
    # carregada, e tocá-la numa sessão assíncrona estoura em MissingGreenlet — já
    # aconteceu no módulo de compras. Quem precisa do plano busca pelo id, explícito.
    cobrancas: Mapped[list["Cobranca"]] = relationship(
        back_populates="assinatura", order_by="Cobranca.competencia"
    )


class Cobranca(TenantMixin, TimestampMixin, Base):
    """A cobrança de um mês.

    Linha gravada, não período deduzido na leitura: o que foi cobrado em março precisa
    continuar sendo o que foi cobrado em março, mesmo que o preço do plano mude em abril.
    Por isso ``valor`` é **cópia** do preço no instante em que a cobrança nasce — a mesma
    distinção do preço do item na venda (ADR 0008).
    """

    __tablename__ = "assinaturas_cobranca"
    __table_args__ = (
        # Uma por competência, por assinatura. É o que torna gerar o mês repetível: rodar
        # duas vezes não cobra duas vezes.
        UniqueConstraint(
            "tenant_id",
            "assinatura_id",
            "competencia",
            name="uq_assinaturas_cobranca_assinatura_competencia",
        ),
        Index("ix_assinaturas_cobranca_tenant_id_status", "tenant_id", "status"),
        Index("ix_assinaturas_cobranca_tenant_id_vencimento", "tenant_id", "vencimento"),
        CheckConstraint("valor >= 0", name="valor_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    assinatura_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assinaturas_assinatura.id", ondelete="CASCADE"),
        nullable=False,
    )
    # O primeiro dia do mês cobrado. Data e não texto: ordena e compara sem conversa.
    competencia: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[StatusCobranca] = mapped_column(
        _enum(StatusCobranca, "assinaturas_status_cobranca"),
        nullable=False,
        default=StatusCobranca.ABERTA,
    )
    pago_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Dinheiro, pix, boleto — texto porque não há gateway, e uma lista fechada agora seria
    # adivinhação sobre como o lojista recebe.
    forma_pagamento: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # ---- prazo de confiança
    #
    # A pessoa liga pedindo mais um dia, e recebe. É ato de gente, nunca automático: prazo
    # que o sistema concede sozinho não é confiança, é outro prazo fixo. Sempre com data de
    # fim — prazo sem fim é perdão de dívida com outro nome. Ver ADR 0013, decisão 4.
    prazo_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    prazo_motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    prazo_por: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    assinatura: Mapped["Assinatura"] = relationship(back_populates="cobrancas")


TENANT_SCOPED_TABLES = (
    Plano.__tablename__,
    Assinatura.__tablename__,
    Cobranca.__tablename__,
)
