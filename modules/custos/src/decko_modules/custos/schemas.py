import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field


class ConsumoIn(BaseModel):
    produto_id: uuid.UUID
    # Obrigatório aqui, e opcional na despesa: um consumo sem centro é uma linha que não
    # responde nada, e este módulo existe para responder contra o quê.
    centro_custo_id: uuid.UUID
    quantidade: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unidade_id: uuid.UUID
    lote_id: uuid.UUID | None = None
    # Em branco, vale o preço de custo do produto — cópia de uma referência, e não
    # avaliação de estoque. Ver ADR 0026, decisão 3.
    valor: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    documento: str | None = Field(default=None, max_length=120)
    observacao: str | None = None
    ocorrido_em: AwareDatetime | None = None


class ConsumoOut(BaseModel):
    id: uuid.UUID
    centro_custo_id: uuid.UUID
    centro_nome: str
    produto_nome: str
    quantidade: Decimal
    valor: Decimal
    custo_unitario: Decimal | None
    ocorrido_em: datetime
    observacao: str | None


class CustoDoCentroOut(BaseModel):
    """O que um centro custou no período, pelas duas fontes."""

    centro_id: uuid.UUID
    nome: str
    consumo: Decimal
    despesa: Decimal
    total: Decimal
