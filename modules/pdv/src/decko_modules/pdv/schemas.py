import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.pdv.models import FormaPagamento, StatusVenda, TipoMovimentoCaixa


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
    # Opcional: o balcão não para para escolher conta — ver ADR 0014, decisão 3.
    conta_id: uuid.UUID | None = None


class PagamentoOut(BaseModel):
    id: uuid.UUID
    forma: FormaPagamento
    valor: Decimal
    conta_id: uuid.UUID | None = None
    # Lido na hora, não copiado: renomear a conta vale para o histórico dela também.
    conta_nome: str | None = None


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

    # Nulo é o caso normal: venda anônima de balcão.
    cliente_id: uuid.UUID | None = None
    # Lido na hora, não copiado: corrigir um nome digitado errado precisa valer para as
    # vendas da pessoa também — ver docs/adr/0008-ponto-de-venda.md.
    cliente_nome: str | None = None

    itens: list[ItemOut]
    pagamentos: list[PagamentoOut]

    soma_dos_itens: Decimal
    desconto: Decimal
    total: Decimal
    pago: Decimal
    falta: Decimal
    troco: Decimal


class IdentificarIn(BaseModel):
    cliente_id: uuid.UUID


class VendaResumoOut(BaseModel):
    """Linha de lista. Sem itens: a lista de vendas do dia não precisa carregá-los."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int | None
    status: StatusVenda
    aberta_em: datetime
    fechada_em: datetime | None
    total: Decimal | None


class LinhaDaFormaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    forma: FormaPagamento
    quantidade: int
    valor: Decimal


class LinhaDaContaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conta_id: uuid.UUID | None
    # Nulo quando o caixa não escolheu conta, que é o caso normal — ver ADR 0014.
    conta_nome: str | None

    valor: Decimal


class LinhaDoOperadorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operador_id: uuid.UUID | None
    operador_nome: str | None
    vendas: int
    valor: Decimal


class ConferenciaOut(BaseModel):
    """O que entrou no período. Leitura, não fechamento de caixa."""

    model_config = ConfigDict(from_attributes=True)

    de: datetime
    ate: datetime
    vendas: int
    canceladas: int
    bruto: Decimal
    descontos: Decimal
    liquido: Decimal
    recebido: Decimal
    por_forma: list[LinhaDaFormaOut]
    por_conta: list[LinhaDaContaOut]
    por_operador: list[LinhaDoOperadorOut]


class AberturaIn(BaseModel):
    # O fundo de troco com que a gaveta começa. Zero é válido: nem toda loja deixa troco.
    abertura: Decimal = Field(ge=0)


class MovimentoCaixaIn(BaseModel):
    tipo: TipoMovimentoCaixa
    valor: Decimal = Field(gt=0)
    # Obrigatório: sangria sem motivo é a linha que ninguém explica depois.
    motivo: str = Field(min_length=1, max_length=200)


class FechamentoCaixaIn(BaseModel):
    contado: Decimal = Field(ge=0)
    observacao: str | None = Field(default=None, max_length=500)


class MovimentoCaixaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: TipoMovimentoCaixa
    valor: Decimal
    motivo: str
    created_at: datetime


class CaixaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    operador_id: uuid.UUID
    aberto_em: datetime
    fechado_em: datetime | None
    abertura: Decimal
    # Preenchidos só no fechamento. Enquanto o caixa está aberto, o esperado é conta feita
    # na leitura — ver `esperado_agora`.
    contado: Decimal | None
    esperado: Decimal | None
    diferenca: Decimal | None
    observacao: str | None
    movimentos: list[MovimentoCaixaOut]
    # O que deveria haver na gaveta neste instante. Some depois de fechado: aí o que vale
    # é o `esperado`, congelado no momento em que a contagem foi feita.
    esperado_agora: Decimal | None
