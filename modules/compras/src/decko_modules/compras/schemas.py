import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.comercial.identidade import Origem
from decko_modules.compras.models import OrigemVinculo, StatusNota


class XmlIn(BaseModel):
    """O conteúdo do arquivo, como texto.

    Chega assim, e não como upload binário, porque é o que a tela tem em mãos: o
    navegador lê o arquivo escolhido e manda o texto. Quando houver caixa de entrada de
    e-mail lendo XML sozinha, ela chama o mesmo serviço.
    """

    xml: str = Field(min_length=1)


class CandidatoOut(BaseModel):
    """Um produto que este item pode ser, com a razão à vista.

    A razão é mostrada na tela: o lojista precisa saber se aquilo veio do código de
    barras ou de um palpite sobre o nome antes de clicar.
    """

    produto_id: uuid.UUID
    nome: str
    origem: Origem
    pontuacao: float
    automatico: bool


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero_item: int
    # Como o fornecedor escreveu.
    codigo_fornecedor: str
    descricao: str
    gtin: str | None
    ncm: str | None
    cest: str | None
    unidade_comercial: str | None
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    # O destino, quando já decidido.
    produto_id: uuid.UUID | None
    origem_vinculo: OrigemVinculo | None
    unidade_id: uuid.UUID | None


class ItemConferidoOut(ItemOut):
    """O item com os palpites, para a tela de conferência."""

    sugestoes: list[CandidatoOut]


class NotaResumoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chave: str
    numero: str | None
    serie: str | None
    emitente_cnpj: str
    emitente_nome: str | None
    emitida_em: datetime | None
    valor_total: Decimal
    status: StatusNota


class NotaOut(NotaResumoOut):
    itens: list[ItemConferidoOut]
    # Quantos itens ainda esperam decisão. A nota não fecha com algum aqui.
    pendentes: int


class VincularIn(BaseModel):
    """Este item da nota é aquele produto do cadastro."""

    produto_id: uuid.UUID
    # Em que embalagem a quantidade entra. Sem ela, usa a unidade base do produto.
    unidade_id: uuid.UUID | None = None


class NovoProdutoIn(BaseModel):
    """Este item não existe no cadastro: vira produto na confirmação da nota."""

    unidade_id: uuid.UUID


class ConfirmacaoOut(BaseModel):
    nota: NotaResumoOut
    produtos_criados: int
    itens_lancados: int
