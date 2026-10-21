import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.comercial.models import TipoMovimento


class UnidadeIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    simbolo: str | None = Field(default=None, max_length=10)
    # Nulo cria a raiz de um sistema de medida. Com referência, descreve uma embalagem.
    referencia_id: uuid.UUID | None = None
    fator_relativo: Decimal = Field(default=Decimal(1), gt=0)


class UnidadeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    simbolo: str | None
    referencia_id: uuid.UUID | None
    fator_relativo: Decimal
    # Quanto vale em relação à raiz: o fardo de 10 caixas de 12 mostra 120.
    fator: Decimal


class CategoriaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    pai_id: uuid.UUID | None = None


class CategoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    pai_id: uuid.UUID | None


class ProdutoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=60)
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = None
    gtin: str | None = Field(default=None, max_length=14, pattern=r"^\d*$")
    categoria_id: uuid.UUID | None = None
    unidade_id: uuid.UUID
    preco_custo: Decimal | None = Field(default=None, ge=0)
    preco_venda: Decimal | None = Field(default=None, ge=0)
    controla_lote: bool = False
    controla_validade: bool = False


class ProdutoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nome: str
    descricao: str | None
    gtin: str | None
    categoria_id: uuid.UUID | None
    unidade_id: uuid.UUID
    preco_custo: Decimal | None
    preco_venda: Decimal | None
    controla_lote: bool
    controla_validade: bool
    ativo: bool


class LoteIn(BaseModel):
    produto_id: uuid.UUID
    codigo: str = Field(min_length=1, max_length=60)
    validade: date | None = None
    fabricacao: date | None = None


class LoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    produto_id: uuid.UUID
    codigo: str
    validade: date | None
    fabricacao: date | None


class MovimentoIn(BaseModel):
    produto_id: uuid.UUID
    tipo: TipoMovimento
    # Sempre positiva: o que define entrada ou saída é o tipo.
    quantidade: Decimal = Field(gt=0)
    # Unidade em que foi digitada — caixa, fardo. O saldo soma na unidade base.
    unidade_id: uuid.UUID
    lote_id: uuid.UUID | None = None
    documento: str | None = Field(default=None, max_length=120)
    motivo: str | None = Field(default=None, max_length=300)
    ocorrido_em: datetime | None = None


class MovimentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    produto_id: uuid.UUID
    lote_id: uuid.UUID | None
    tipo: TipoMovimento
    quantidade: Decimal
    quantidade_digitada: Decimal
    unidade_id: uuid.UUID
    documento: str | None
    motivo: str | None
    ocorrido_em: datetime


class SaldoOut(BaseModel):
    produto_id: uuid.UUID
    unidade_id: uuid.UUID
    quantidade: Decimal
    por_lote: list["SaldoLoteOut"]


class SaldoLoteOut(BaseModel):
    lote_id: uuid.UUID | None
    codigo: str | None
    validade: date | None
    quantidade: Decimal
