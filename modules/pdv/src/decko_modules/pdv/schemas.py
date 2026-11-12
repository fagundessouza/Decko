import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from decko_modules.pdv.models import (
    AcaoAutorizada,
    DestinoDevolucao,
    FormaPagamento,
    StatusVenda,
    TipoMovimentoCaixa,
)


class CredencialIn(BaseModel):
    """Quem está liberando, e o segredo dele: a senha **ou** o PIN.

    Vai **junto com a ação** de propósito: o servidor confere e executa na mesma
    requisição. Destravar a tela e confiar nela seria teatro — ver
    `docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 4.

    O PIN existe aqui porque é no balcão que isto acontece: o supervisor chamado para
    liberar um cancelamento não digita uma senha longa com a fila esperando.
    """

    autorizador_id: uuid.UUID
    senha: str | None = Field(default=None, min_length=1, max_length=256)
    pin: str | None = Field(default=None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def _um_segredo_so(self) -> "CredencialIn":
        if (self.senha is None) == (self.pin is None):
            raise ValueError("Informe a senha ou o PIN de quem libera, um dos dois.")
        return self


class AutorizadorOut(BaseModel):
    """Só o nome sai daqui. A senha é o que libera, não a lista."""

    id: uuid.UUID
    nome: str


class ConfiguracaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exige_cancelar_item: bool
    exige_cancelar_venda: bool
    exige_sangria: bool
    exige_devolucao: bool
    exige_desconto: bool
    desconto_livre: Decimal
    exige_diferenca: bool
    diferenca_livre: Decimal


class ConfiguracaoIn(BaseModel):
    exige_cancelar_item: bool
    exige_cancelar_venda: bool
    exige_sangria: bool
    exige_devolucao: bool
    exige_desconto: bool
    desconto_livre: Decimal = Field(ge=0)
    exige_diferenca: bool
    diferenca_livre: Decimal = Field(ge=0)


class AutorizacaoExigidaOut(BaseModel):
    """O corpo do 428: diz à tela o que pedir, em vez de mostrar um erro ao operador."""

    detail: str
    acao: AcaoAutorizada


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
    # Acima do limite da loja, só com supervisor.
    autorizacao: CredencialIn | None = None


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


class LinhaDeAvariaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    produto_id: uuid.UUID
    descricao: str
    unidade_id: uuid.UUID
    # Agrupado por produto **e** unidade, sem converter embalagem: somar "2 caixas" com
    # "3 unidades" num número só daria um total que não existe.
    unidade_simbolo: str | None
    quantidade: Decimal


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

    # O que voltou. Sem isto a gaveta nunca fecha numa loja que devolve.
    devolucoes: int
    devolvido: Decimal
    devolvido_em_especie: Decimal
    # O que voltou com defeito e **não** entrou no estoque vendável: a pilha de RMA.
    avarias: list[LinhaDeAvariaOut]


class AberturaIn(BaseModel):
    # O fundo de troco com que a gaveta começa. Zero é válido: nem toda loja deixa troco.
    abertura: Decimal = Field(ge=0)


class MovimentoCaixaIn(BaseModel):
    tipo: TipoMovimentoCaixa
    valor: Decimal = Field(gt=0)
    # Obrigatório: sangria sem motivo é a linha que ninguém explica depois.
    motivo: str = Field(min_length=1, max_length=200)
    # Só a sangria pede liberação: dinheiro entrando na gaveta não é o que se desvia.
    autorizacao: CredencialIn | None = None


class FechamentoCaixaIn(BaseModel):
    contado: Decimal = Field(ge=0)
    observacao: str | None = Field(default=None, max_length=500)
    # Diferença acima do limite da loja só fecha com supervisor. É a única trava deste
    # tipo que o Odoo tem de fábrica.
    autorizacao: CredencialIn | None = None


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
    # Preenchidos só no fechamento, e **não** há campo de esperado enquanto o caixa está
    # aberto: devolvê-lo bastaria abrir o inspetor para ver o número antes de contar, e a
    # conferência cega da ADR 0008 vale também na rede.
    contado: Decimal | None
    esperado: Decimal | None
    diferenca: Decimal | None
    observacao: str | None
    movimentos: list[MovimentoCaixaOut]


# ------------------------------------------------------------------- devolução de venda


class LinhaDevolverIn(BaseModel):
    """Uma linha da venda voltando.

    ``destino`` tem padrão ``estoque`` porque é o caso comum — o que volta, volta para
    vender. ``avaria`` é a exceção que precisa ser dita, e é ela que separa a pilha de RMA.
    """

    venda_item_id: uuid.UUID
    quantidade: Decimal = Field(gt=0)
    destino: DestinoDevolucao = DestinoDevolucao.ESTOQUE


class DevolucaoIn(BaseModel):
    itens: list[LinhaDevolverIn] = Field(min_length=1)
    # Dinheiro saindo da gaveta sem venda por trás: pede liberação quando a loja exige.
    autorizacao: CredencialIn | None = None
    # Como o dinheiro volta. Só `dinheiro` sai da gaveta; cartão e Pix ficam registrados na
    # forma original, porque o estorno é da adquirente.
    forma: FormaPagamento
    # Obrigatório, pela razão da sangria: devolução que ninguém explica depois é justamente
    # a que importa explicar.
    motivo: str = Field(min_length=1, max_length=300)


class PreviaDevolucaoIn(BaseModel):
    """A prévia não pede motivo: ela só diz quanto sai, e nada é gravado."""

    itens: list[LinhaDevolverIn] = Field(min_length=1)


class ItemDevolucaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venda_item_id: uuid.UUID
    quantidade: Decimal
    valor: Decimal
    destino: DestinoDevolucao


class DevolucaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venda_id: uuid.UUID
    operador_id: uuid.UUID | None
    # Nulo quando quem registrou não tinha caixa aberto: a devolução fica fora de sessão,
    # registrada e visível, pela mesma razão que a venda fora de sessão.
    caixa_id: uuid.UUID | None
    forma: FormaPagamento
    motivo: str
    total: Decimal
    created_at: datetime
    itens: list[ItemDevolucaoOut]


class PreviaDevolucaoOut(BaseModel):
    """Quanto sai da gaveta, conferido pelo servidor e sem nada gravado.

    O operador vê o valor **antes** de devolver o dinheiro, e o valor vem de onde vem o
    total da venda: do servidor — ver ADR 0008, decisão 3.
    """

    total: Decimal
    valores: list[Decimal]


class LinhaDevolvivelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    venda_item_id: uuid.UUID
    descricao: str
    unidade_id: uuid.UUID
    quantidade: Decimal
    devolvida: Decimal
    resta: Decimal
    # Quanto sai da gaveta se esta linha voltar inteira.
    valor_resta: Decimal


class DevolucoesDaVendaOut(BaseModel):
    """O que a tela de devolução precisa de uma venda, numa resposta só."""

    venda_id: uuid.UUID
    numero: int | None
    fechada_em: datetime | None
    total: Decimal
    linhas: list[LinhaDevolvivelOut]
    devolucoes: list[DevolucaoOut]
    devolvido: Decimal


class RetirarItemIn(BaseModel):
    """Tirar item de venda em andamento é o caso que o dono do projeto descreveu.

    Virou `POST` com corpo porque a credencial não pode viajar em `DELETE`: corpo em
    `DELETE` é mal suportado por intermediário, e senha em parâmetro de URL acaba em log.
    """

    autorizacao: CredencialIn | None = None


class CancelarVendaIn(BaseModel):
    autorizacao: CredencialIn | None = None
