"""Ponto de venda: a venda de balcão e o que ela movimenta.

O PDV não tem cadastro próprio de produto, de estoque nem de cliente: usa os dos módulos
``comercial`` e ``clientes``, que ele declara em ``depends`` — ver
``docs/adr/0007-dependencia-entre-modulos.md``.

O que ficou de fora de propósito, e por quê, está em ``docs/adr/0008-ponto-de-venda.md``.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class StatusVenda(StrEnum):
    ABERTA = "aberta"
    FINALIZADA = "finalizada"
    CANCELADA = "cancelada"


class FormaPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    DEBITO = "debito"
    CREDITO = "credito"
    PIX = "pix"
    # Vale-refeição, convênio, o que a loja aceitar. Existe para a venda não travar por
    # falta de uma opção; a lista fechada vem com o módulo fiscal, que tem a tabela certa.
    OUTRO = "outro"


def _enum(python_enum: type, name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Contador(Base):
    """O próximo número de venda de cada empresa.

    Uma linha por empresa, incrementada em ``INSERT ... ON CONFLICT DO UPDATE RETURNING``:
    é o banco que serializa dois caixas fechando junto, e não a aplicação. Contar
    ``max(numero) + 1`` daria o mesmo número aos dois.

    Não usa ``TenantMixin`` porque aqui a empresa é a própria chave primária — uma coluna
    de identidade artificial permitiria duas linhas para a mesma empresa, que é
    exatamente o que não pode existir.
    """

    __tablename__ = "pdv_contador"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    )
    proximo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Venda(TenantMixin, TimestampMixin, Base):
    """Uma venda de balcão.

    ``numero`` só é atribuído ao finalizar: enquanto aberta a venda é identificada pelo
    id. Numerar na abertura gastaria número em venda abandonada, e o número é o que o
    cliente vê no cupom.
    """

    __tablename__ = "pdv_venda"
    __table_args__ = (
        UniqueConstraint("tenant_id", "numero", name="uq_pdv_venda_tenant_id_numero"),
        Index("ix_pdv_venda_tenant_id_status", "tenant_id", "status"),
        Index("ix_pdv_venda_tenant_id_fechada_em", "tenant_id", "fechada_em"),
        CheckConstraint("desconto >= 0", name="desconto_nao_negativo"),
        CheckConstraint("total IS NULL OR total >= 0", name="total_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[StatusVenda] = mapped_column(
        _enum(StatusVenda, "pdv_status_venda"), nullable=False, default=StatusVenda.ABERTA
    )

    # Desconto sobre a venda inteira, além do que cada item possa ter.
    desconto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal(0))

    # Congelado ao finalizar. Enquanto a venda está aberta o total é a soma dos itens, que
    # ainda muda; depois de fechada ele é o que o cliente pagou, e não pode acompanhar uma
    # mudança de preço do produto no cadastro.
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    aberta_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    operador_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    # Quem comprou, quando a venda é identificada. Nulo é o caso normal: exigir CPF para
    # vender um pão travaria o balcão.
    #
    # `RESTRICT` e não `SET NULL`: o cadastro de clientes nunca apaga, só desativa,
    # justamente para a venda continuar apontando para alguém. Aqui o banco cobra essa
    # promessa. Ver a atualização de 29/10/2026 em docs/adr/0008-ponto-de-venda.md.
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes_cliente.id", ondelete="RESTRICT"),
        nullable=True,
    )
    observacao: Mapped[str | None] = mapped_column(String(300), nullable=True)

    itens: Mapped[list["ItemVenda"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan", order_by="ItemVenda.created_at"
    )
    pagamentos: Mapped[list["Pagamento"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan", order_by="Pagamento.created_at"
    )


class ItemVenda(TenantMixin, TimestampMixin, Base):
    """Uma linha da venda.

    ``preco_unitario`` é cópia, não referência: mudar o preço no cadastro amanhã não pode
    mudar o que foi vendido hoje.
    """

    __tablename__ = "pdv_venda_item"
    __table_args__ = (
        Index("ix_pdv_venda_item_venda_id", "venda_id"),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
        CheckConstraint("preco_unitario >= 0", name="preco_nao_negativo"),
        CheckConstraint("desconto >= 0", name="desconto_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    venda_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_venda.id", ondelete="CASCADE"), nullable=False
    )

    # Do módulo comercial. A chave estrangeira existe porque é o banco que garante que o
    # produto não some debaixo de uma venda já fechada.
    produto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_produto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lote_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comercial_lote.id", ondelete="RESTRICT"), nullable=True
    )
    unidade_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_unidade.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Na unidade digitada: vender "2 caixas" é guardado como 2, com a unidade caixa. A
    # conversão para a unidade base acontece na baixa de estoque, no módulo comercial.
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    desconto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal(0))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Cópia do nome no momento da venda, pelo mesmo motivo do preço: o cupom reimpresso
    # precisa dizer o que foi vendido, não o que o produto se chama hoje.
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)

    venda: Mapped["Venda"] = relationship(back_populates="itens")


class Pagamento(TenantMixin, TimestampMixin, Base):
    """Uma forma de pagamento usada na venda. Uma venda pode ter várias."""

    __tablename__ = "pdv_pagamento"
    __table_args__ = (
        Index("ix_pdv_pagamento_venda_id", "venda_id"),
        CheckConstraint("valor > 0", name="valor_positivo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    venda_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_venda.id", ondelete="CASCADE"), nullable=False
    )
    forma: Mapped[FormaPagamento] = mapped_column(
        _enum(FormaPagamento, "pdv_forma_pagamento"), nullable=False
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Em qual conta o dinheiro caiu. A forma diz **como** o cliente pagou; isto diz
    # **onde** — e é a segunda pergunta que não fecha no fim do dia, porque duas chaves Pix
    # da mesma loja são dois destinos.
    #
    # Nulo por padrão, e nada no caixa trava por causa dele: velocidade de balcão é
    # requisito. Ver docs/adr/0014-conta-de-recebimento.md, decisão 3.
    conta_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financeiro_conta.id", ondelete="RESTRICT"),
        nullable=True,
    )

    venda: Mapped["Venda"] = relationship(back_populates="pagamentos")


TENANT_SCOPED_TABLES = (
    Contador.__tablename__,
    Venda.__tablename__,
    ItemVenda.__tablename__,
    Pagamento.__tablename__,
)
