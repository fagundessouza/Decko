"""A nota do fornecedor enquanto ela ainda não virou estoque.

Nota importada fica em rascunho até o lojista conferir item por item. Nenhum produto é
criado e nenhum movimento é lançado antes disso — ver
``docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md``, decisão 4.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class StatusNota(StrEnum):
    RASCUNHO = "rascunho"
    CONFIRMADA = "confirmada"
    DESCARTADA = "descartada"


class OrigemVinculo(StrEnum):
    """Por que este item ficou ligado a este produto. É o que a tela explica ao lojista."""

    GTIN = "gtin"
    FORNECEDOR = "fornecedor"
    # Escolhido na tela, entre os sugeridos ou procurando.
    MANUAL = "manual"
    # Produto não existia: será cadastrado a partir da própria nota.
    NOVO = "novo"


def _enum(python_enum: type, name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Nota(TenantMixin, TimestampMixin, Base):
    """Uma nota fiscal de entrada, importada do XML."""

    __tablename__ = "compras_nota"
    __table_args__ = (
        # A chave de acesso identifica a nota no país inteiro. Importar duas vezes a mesma
        # nota dobraria o estoque, e é erro fácil de cometer com arquivo no e-mail.
        UniqueConstraint("tenant_id", "chave", name="uq_compras_nota_tenant_id_chave"),
        Index("ix_compras_nota_tenant_id_status", "tenant_id", "status"),
        CheckConstraint("valor_total >= 0", name="valor_total_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    # 44 dígitos. Guardada sem máscara, como todo documento no sistema.
    chave: Mapped[str] = mapped_column(String(44), nullable=False)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    serie: Mapped[str | None] = mapped_column(String(10), nullable=True)

    emitente_cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    emitente_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emitida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal(0))
    status: Mapped[StatusNota] = mapped_column(
        _enum(StatusNota, "compras_status_nota"), nullable=False, default=StatusNota.RASCUNHO
    )
    confirmada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmada_por: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    # O XML como chegou. É o documento, não uma cópia dele: quando o saldo não bater, a
    # pergunta é "o que a nota dizia", e a resposta precisa existir. Custa alguns KB por
    # nota, e é o mesmo princípio do payload de clima guardado no agro.
    xml_origem: Mapped[str] = mapped_column(Text, nullable=False)

    itens: Mapped[list["NotaItem"]] = relationship(
        back_populates="nota", cascade="all, delete-orphan", order_by="NotaItem.numero_item"
    )


class NotaItem(TenantMixin, TimestampMixin, Base):
    """Uma linha da nota, com o que o fornecedor escreveu e o produto que ela virou.

    Os campos do fornecedor são guardados como vieram, sem tradução. É deles que sai a
    equivalência que faz a próxima nota entrar sozinha.
    """

    __tablename__ = "compras_nota_item"
    __table_args__ = (
        UniqueConstraint("nota_id", "numero_item", name="uq_compras_nota_item_numero"),
        Index("ix_compras_nota_item_nota_id", "nota_id"),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    nota_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("compras_nota.id", ondelete="CASCADE"), nullable=False
    )
    numero_item: Mapped[int] = mapped_column(Integer, nullable=False)

    # Como o fornecedor descreve: cProd, xProd, cEAN, NCM e CEST do item da NF-e.
    codigo_fornecedor: Mapped[str] = mapped_column(String(60), nullable=False)
    descricao: Mapped[str] = mapped_column(String(300), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)
    ncm: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cest: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # A unidade como está escrita na nota ("UN", "CX", "FD"). É texto livre do emitente,
    # não referência: o que ela significa em unidades só o lojista sabe dizer.
    unidade_comercial: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Preenchido quando o item já foi reconhecido. Nulo é item esperando decisão.
    produto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comercial_produto.id", ondelete="RESTRICT"), nullable=True
    )
    origem_vinculo: Mapped[OrigemVinculo | None] = mapped_column(
        _enum(OrigemVinculo, "compras_origem_vinculo"), nullable=True
    )
    # Em qual embalagem a quantidade entra no estoque. Nulo usa a unidade base do produto.
    # A nota diz "CX"; quantas unidades tem a caixa, ela não diz.
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comercial_unidade.id", ondelete="RESTRICT"), nullable=True
    )

    nota: Mapped["Nota"] = relationship(back_populates="itens")


TENANT_SCOPED_TABLES = (
    Nota.__tablename__,
    NotaItem.__tablename__,
)


# Usado pelo serviço ao lançar o movimento de entrada. Fica aqui para o texto do documento
# na razão de estoque ser um só, e não dois literais parecidos em arquivos diferentes.
def documento_de(nota: Nota) -> str:
    return f"NF {nota.numero or nota.chave[-9:]}"
