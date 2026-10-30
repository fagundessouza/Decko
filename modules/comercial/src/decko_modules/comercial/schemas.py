import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from decko.fiscal import pydantic_optional_cest, pydantic_optional_ncm
from decko_modules.comercial.models import TipoMovimento

# Aceita digitado com ou sem máscara e guarda só os dígitos. Em branco é ausência de
# código, não erro — ver apps/api/src/decko/fiscal.py.
OptionalNcm = Annotated[str | None, BeforeValidator(pydantic_optional_ncm)]
OptionalCest = Annotated[str | None, BeforeValidator(pydantic_optional_cest)]


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
    # O código é o SKU: é com ele que a loja chama o produto e o cliente confere o que
    # chegou. Não existe um campo "sku" ao lado — seriam duas verdades para a mesma coisa.
    codigo: str = Field(min_length=1, max_length=60)
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = None
    gtin: str | None = Field(default=None, max_length=14, pattern=r"^\d*$")
    # Classificação fiscal. Quem compra por licitação pede o NCM antes do preço.
    ncm: OptionalNcm = None
    cest: OptionalCest = None
    categoria_id: uuid.UUID | None = None
    unidade_id: uuid.UUID
    preco_custo: Decimal | None = Field(default=None, ge=0)
    preco_venda: Decimal | None = Field(default=None, ge=0)
    controla_lote: bool = False
    controla_validade: bool = False
    # Abaixo disto o produto entra na lista do que está acabando. Nulo é "não avise".
    estoque_minimo: Decimal | None = Field(default=None, ge=0)


class ProdutoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nome: str
    descricao: str | None
    gtin: str | None
    ncm: str | None
    cest: str | None
    categoria_id: uuid.UUID | None
    unidade_id: uuid.UUID
    preco_custo: Decimal | None
    preco_venda: Decimal | None
    controla_lote: bool
    controla_validade: bool
    estoque_minimo: Decimal | None
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


class ProdutoAcabandoOut(BaseModel):
    produto_id: uuid.UUID
    codigo: str
    nome: str
    saldo: Decimal
    estoque_minimo: Decimal
    # Zerou de vez, em vez de só estar perto do mínimo. A tela trata diferente.
    acabou: bool


class LoteVencendoOut(BaseModel):
    produto_id: uuid.UUID
    produto_nome: str
    lote_id: uuid.UUID
    lote_codigo: str
    validade: date
    saldo: Decimal
    vencido: bool


class AlertasOut(BaseModel):
    """O que o dono precisa ver antes de o problema acontecer."""

    acabando: list[ProdutoAcabandoOut]
    vencendo: list[LoteVencendoOut]
    total: int
    # Quantos dias à frente a lista de validade olhou. A tela conta isso a quem lê.
    dias: int
