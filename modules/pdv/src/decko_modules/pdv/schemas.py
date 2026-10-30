import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.pdv.models import FormaPagamento, StatusVenda


class ItemIn(BaseModel):
    produto_id: uuid.UUID
    quantidade: Decimal = Field(gt=0)
    # Sem unidade, vende na unidade base do produto. Com unidade, vende "2 caixas".
    unidade_id: uuid.UUID | None = None
    lote_id: uuid.UUID | None = None
    # Preço avulso, para quando o caixa tem autorização de alterar. Sem ele, usa o cadastro.
    preco_unitario: Decimal | None = Field(default=None, ge=0)
    desconto: Decimal = Field(default=Decimal(0), ge=0)


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    produto_id: uuid.UUID
    lote_id: uuid.UUID | None
    unidade_id: uuid.UUID
    descricao: str
    quantidade: Decimal
    preco_unitario: Decimal
    desconto: Decimal
    total: Decimal


class PagamentoIn(BaseModel):
    forma: FormaPagamento
    valor: Decimal = Field(gt=0)


class PagamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    forma: FormaPagamento
    valor: Decimal


class DescontoIn(BaseModel):
    desconto: Decimal = Field(ge=0)


class VendaOut(BaseModel):
    """A venda como o caixa a enxerga, com as contas já feitas.

    ``total`` e ``falta`` vêm calculados do servidor em vez de somados na tela: duas somas
    do mesmo dinheiro em lugares diferentes divergem, e a que o cliente paga é esta.
    """

    id: uuid.UUID
    numero: int | None
    status: StatusVenda
    aberta_em: datetime
    fechada_em: datetime | None
    observacao: str | None

    itens: list[ItemOut]
    pagamentos: list[PagamentoOut]

    soma_dos_itens: Decimal
    desconto: Decimal
    total: Decimal
    pago: Decimal
    falta: Decimal
    troco: Decimal


class VendaResumoOut(BaseModel):
    """Linha de lista. Sem itens: a lista de vendas do dia não precisa carregá-los."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int | None
    status: StatusVenda
    aberta_em: datetime
    fechada_em: datetime | None
    total: Decimal | None
