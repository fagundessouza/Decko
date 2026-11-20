"""Consumo interno: o que saiu do estoque sem ser venda, e contra o quê.

O adubo que foi para o talhão, o diesel que foi para o trator, a embalagem que a loja
gastou. É a metade da pergunta "quanto custou o hectare" que não está nas contas a pagar.

Decisões e limites: ``docs/adr/0026-consumo-interno-e-custo-por-centro.md``.
"""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class Consumo(TenantMixin, TimestampMixin, Base):
    """A anotação que liga uma saída de estoque a um centro de custo.

    **Anotação, e não movimento paralelo.** Quantidade, produto, lote e data vivem no
    movimento do ``comercial``; copiá-los aqui criaria duas verdades que divergem na
    primeira correção. O relatório paga um ``join``, que é o preço certo — ver ADR 0026,
    decisão 2.
    """

    __tablename__ = "custos_consumo"
    __table_args__ = (
        # Um movimento tem no máximo um consumo: lançar duas vezes contra centros
        # diferentes faria o mesmo adubo custar duas vezes.
        UniqueConstraint("tenant_id", "movimento_id", name="uq_custos_consumo_movimento"),
        Index("ix_custos_consumo_tenant_id_centro", "tenant_id", "centro_custo_id"),
        CheckConstraint("valor >= 0", name="valor_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()

    # RESTRICT nos dois: nem a razão de estoque nem o centro desaparecem por baixo de um
    # custo já lançado.
    movimento_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_movimento.id", ondelete="RESTRICT"),
        nullable=False,
    )
    centro_custo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financeiro_centro_custo.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # O que custou. Cópia do preço de custo no instante do lançamento, e **não** avaliação
    # de estoque: não é PEPS, não é custo médio, não é contabilidade — ADR 0026, decisão 3.
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Gravado junto, e não deduzido do produto na leitura: o preço de custo muda, e o
    # consumo do mês passado não deve mudar com ele.
    custo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sem `relationship` para o centro nem para o movimento, de propósito: ligar classes de
    # outro módulo por nome depende da ordem de importação e quebra quando o módulo irmão
    # não está carregado. As consultas que precisam dos dois fazem o `join` explícito.


TENANT_SCOPED_TABLES = (Consumo.__tablename__,)
