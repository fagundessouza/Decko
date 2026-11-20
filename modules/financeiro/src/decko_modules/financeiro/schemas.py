import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.financeiro.models import StatusDespesa


class ContaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    instituicao: str | None = Field(default=None, max_length=120)
    # Texto livre: chave Pix é CPF, CNPJ, e-mail, telefone ou aleatória.
    chave_pix: str | None = Field(default=None, max_length=200)


class ContaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    instituicao: str | None
    chave_pix: str | None
    ativa: bool


class CentroIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)


class CentroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    ativo: bool


class DespesaIn(BaseModel):
    descricao: str = Field(min_length=1, max_length=200)
    valor: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    vencimento: date
    fornecedor_nome: str | None = Field(default=None, max_length=200)
    fornecedor_cpf_cnpj: str | None = Field(default=None, max_length=14)
    centro_custo_id: uuid.UUID | None = None
    observacao: str | None = None


class DespesaPatch(BaseModel):
    """Correção de despesa em aberto. Campo ausente é campo que não muda."""

    descricao: str | None = Field(default=None, min_length=1, max_length=200)
    valor: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    vencimento: date | None = None
    fornecedor_nome: str | None = Field(default=None, max_length=200)
    fornecedor_cpf_cnpj: str | None = Field(default=None, max_length=14)
    centro_custo_id: uuid.UUID | None = None
    observacao: str | None = None


class BaixaIn(BaseModel):
    pago_em: date
    # Ausente vira o valor devido: pagar o que estava na conta é o caso comum e não deve
    # dar trabalho. Ver ADR 0024, decisão 5.
    valor_pago: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    conta_id: uuid.UUID | None = None


class DespesaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descricao: str
    fornecedor_nome: str | None
    fornecedor_cpf_cnpj: str | None
    valor: Decimal
    vencimento: date
    status: StatusDespesa
    pago_em: date | None
    valor_pago: Decimal | None
    conta_id: uuid.UUID | None
    centro_custo_id: uuid.UUID | None
    observacao: str | None


class PorCentroOut(BaseModel):
    """A soma de um centro. ``centro_id`` em branco é a despesa sem centro."""

    centro_id: uuid.UUID | None
    nome: str
    em_aberto: Decimal
    pago: Decimal


class ResumoOut(BaseModel):
    """Quanto vence no período, quanto já saiu, o que passou do prazo, e contra o quê."""

    em_aberto: Decimal
    pago: Decimal
    vencido: Decimal
    quantidade_em_aberto: int
    por_centro: list[PorCentroOut]
