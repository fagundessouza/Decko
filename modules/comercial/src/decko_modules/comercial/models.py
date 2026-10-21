"""Base comercial: unidade, categoria, produto, lote e razão de estoque.

Decisões e o que ficou de fora de propósito: ``docs/adr/0006-base-comercial.md``.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class TipoMovimento(StrEnum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    # Correção de contagem. Existe porque a razão não aceita edição do passado: divergência
    # vira lançamento novo, com motivo, e não um número reescrito.
    AJUSTE = "ajuste"


def _enum(python_enum: type, name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Unidade(TenantMixin, TimestampMixin, Base):
    """Unidade de medida, organizada em árvore.

    Cada unidade diz quanto vale em relação à sua unidade de referência, e ``fator`` é o
    produto recursivo até a raiz. É assim que "fardo com 10 caixas de 12" vira 120 sem
    ninguém precisar fazer a conta:

        Unidade (raiz, fator 1)
        └── Caixa, relativo 12 à Unidade      → fator 12
            └── Fardo, relativo 10 à Caixa    → fator 120

    O lojista descreve a embalagem como a enxerga: o fardo é definido em caixas.
    """

    __tablename__ = "comercial_unidade"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nome", name="uq_comercial_unidade_tenant_id_nome"),
        CheckConstraint("fator_relativo > 0", name="fator_relativo_positivo"),
        CheckConstraint("fator > 0", name="fator_positivo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    nome: Mapped[str] = mapped_column(String(60), nullable=False)
    simbolo: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Nulo significa raiz da árvore: a unidade de referência do seu próprio sistema.
    referencia_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_unidade.id", ondelete="RESTRICT"),
        nullable=True,
    )
    fator_relativo: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(1)
    )
    # Absoluto em relação à raiz. Gravado, e não calculado a cada leitura, porque entra em
    # consulta de saldo.
    fator: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Raiz da árvore, denormalizada. Duas unidades só convertem entre si se compartilham a
    # raiz — é o que impede quilo de virar unidade. Guardada para a conferência não ter de
    # subir a árvore a cada conversão. A raiz aponta para si mesma.
    raiz_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    referencia: Mapped["Unidade | None"] = relationship(remote_side="Unidade.id")


class Categoria(TenantMixin, TimestampMixin, Base):
    """Categoria de produto, em árvore."""

    __tablename__ = "comercial_categoria"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nome", "pai_id", name="uq_comercial_categoria_nome_pai"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    pai_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_categoria.id", ondelete="RESTRICT"),
        nullable=True,
    )

    pai: Mapped["Categoria | None"] = relationship(remote_side="Categoria.id")


class Produto(TenantMixin, TimestampMixin, Base):
    """Item comercializado.

    Sem grade de variantes: parafuso 3mm e 4mm são dois produtos enquanto ninguém pedir
    variação — ver ADR 0006, decisão 5.
    """

    __tablename__ = "comercial_produto"
    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_comercial_produto_tenant_id_codigo"),
        # GTIN é único quando existe; produto sem código de barras é comum e permitido.
        UniqueConstraint("tenant_id", "gtin", name="uq_comercial_produto_tenant_id_gtin"),
        Index("ix_comercial_produto_tenant_id_nome", "tenant_id", "nome"),
        CheckConstraint("preco_venda IS NULL OR preco_venda >= 0", name="preco_venda_nao_negativo"),
        CheckConstraint("preco_custo IS NULL OR preco_custo >= 0", name="preco_custo_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Código de barras. Chamado GTIN porque EAN-13, UPC e DUN-14 são todos GTIN.
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)

    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_categoria.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Unidade em que o saldo é somado. A entrada pode ser digitada em caixa ou fardo.
    unidade_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_unidade.id", ondelete="RESTRICT"),
        nullable=False,
    )

    preco_custo: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    preco_venda: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Supermercado precisa, ferragista não. Quem exige é o produto.
    controla_lote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    controla_validade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    categoria: Mapped["Categoria | None"] = relationship()
    unidade: Mapped["Unidade"] = relationship()


class Lote(TenantMixin, TimestampMixin, Base):
    """Lote de um produto, com validade opcional."""

    __tablename__ = "comercial_lote"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "produto_id", "codigo", name="uq_comercial_lote_produto_codigo"
        ),
        Index("ix_comercial_lote_tenant_id_validade", "tenant_id", "validade"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    produto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_produto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    fabricacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    produto: Mapped["Produto"] = relationship()


class Movimento(TenantMixin, Base):
    """Uma linha da razão de estoque. Somente inserção.

    Não existe coluna de quantidade atual: o saldo é a soma daqui. Uma quantidade mutável
    diverge da realidade sem que ninguém saiba quando nem por quê, e a razão responde
    "por que o saldo é esse" — a pergunta que o dono faz quando a contagem não bate.

    ``quantidade`` está sempre na unidade base do produto. ``quantidade_digitada`` e
    ``unidade_id`` preservam o que foi efetivamente lançado, para o documento poder dizer
    "entraram 10 fardos" enquanto o saldo soma em unidades.
    """

    __tablename__ = "comercial_movimento"
    __table_args__ = (
        Index("ix_comercial_movimento_saldo", "tenant_id", "produto_id", "lote_id"),
        Index("ix_comercial_movimento_tenant_id_ocorrido_em", "tenant_id", "ocorrido_em"),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    produto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_produto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lote_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comercial_lote.id", ondelete="RESTRICT"), nullable=True
    )

    tipo: Mapped[TipoMovimento] = mapped_column(
        _enum(TipoMovimento, "comercial_tipo_movimento"), nullable=False
    )
    # Sempre positiva; o sinal vem do tipo. Guardar negativo convidaria a somar errado.
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    quantidade_digitada: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unidade_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_unidade.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # De onde veio: número da nota, cupom, contagem. Texto livre enquanto não houver
    # módulo de compra ou venda para referenciar.
    documento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)

    ocorrido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    registrado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    registrado_por: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    produto: Mapped["Produto"] = relationship()
    lote: Mapped["Lote | None"] = relationship()
    unidade: Mapped["Unidade"] = relationship()


TENANT_SCOPED_TABLES = (
    Unidade.__tablename__,
    Categoria.__tablename__,
    Produto.__tablename__,
    Lote.__tablename__,
    Movimento.__tablename__,
)
