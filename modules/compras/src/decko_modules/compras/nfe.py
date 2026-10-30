"""Leitura do XML da NF-e e da NFC-e.

O layout é o da nota fiscal eletrônica, versão 4.00, publicado pela SEFAZ. O que é lido
aqui é o mínimo para dar entrada de mercadoria: quem emitiu, qual é a nota e o que veio
nela. Imposto não é lido — cálculo fiscal é outro módulo, e não existe ainda.

Caminhos usados, para quem for conferir contra o manual:

- ``infNFe/@Id``           chave de acesso, prefixada por "NFe"
- ``ide/nNF``, ``ide/serie``, ``ide/dhEmi``
- ``emit/CNPJ``, ``emit/xNome``
- ``det/prod``: ``cProd``, ``xProd``, ``cEAN``, ``NCM``, ``CEST``, ``uCom``, ``qCom``,
  ``vUnCom``, ``vProd``
- ``total/ICMSTot/vNF``

O arquivo pode vir como ``nfeProc`` (nota já autorizada, que é o que o fornecedor manda)
ou como ``NFe`` solta. Os dois são aceitos.

**Segurança.** O XML vem de fora, por e-mail, e é lido com ``defusedxml``: o parser padrão
da biblioteca aceita entidades externas, e um arquivo preparado consegue ler arquivo do
servidor ou travar o processo com expansão de entidade.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree

NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
CHAVE_LENGTH = 44
# O emitente escreve isto quando o produto não tem código de barras. É texto, não código.
SEM_GTIN = {"SEM GTIN", "SEMGTIN", ""}


class NotaInvalidaError(ValueError):
    """O arquivo não é uma NF-e legível. A mensagem vai para a tela de quem importou."""


@dataclass(frozen=True)
class ItemLido:
    numero: int
    codigo_fornecedor: str
    descricao: str
    gtin: str | None
    ncm: str | None
    cest: str | None
    unidade_comercial: str | None
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal


@dataclass(frozen=True)
class NotaLida:
    chave: str
    numero: str | None
    serie: str | None
    emitente_cnpj: str
    emitente_nome: str | None
    emitida_em: datetime | None
    valor_total: Decimal
    itens: tuple[ItemLido, ...]


def _texto(elemento, caminho: str) -> str | None:  # type: ignore[no-untyped-def]
    achado = elemento.find(caminho, {"nfe": NAMESPACE})
    if achado is None or achado.text is None:
        return None
    limpo = achado.text.strip()
    return limpo or None


def _decimal(elemento, caminho: str, *, padrao: Decimal = Decimal(0)) -> Decimal:  # type: ignore[no-untyped-def]
    bruto = _texto(elemento, caminho)
    if bruto is None:
        return padrao
    try:
        return Decimal(bruto)
    except InvalidOperation as exc:
        raise NotaInvalidaError(f"Número inválido no XML: '{bruto}'.") from exc


def _digitos(valor: str | None) -> str | None:
    if valor is None:
        return None
    apenas = "".join(caractere for caractere in valor if caractere.isdigit())
    return apenas or None


def _gtin(bruto: str | None) -> str | None:
    """``SEM GTIN`` é como o emitente diz que o produto não tem código de barras."""
    if bruto is None or bruto.strip().upper() in SEM_GTIN:
        return None
    return _digitos(bruto)


def _emitida_em(bruto: str | None) -> datetime | None:
    if bruto is None:
        return None
    try:
        return datetime.fromisoformat(bruto)
    except ValueError:
        # Data ilegível não invalida a nota inteira: ela é informação, não identidade.
        return None


def ler(xml: str | bytes) -> NotaLida:
    """Lê o XML e devolve a nota. Levanta ``NotaInvalidaError`` com o motivo."""
    try:
        raiz = ElementTree.fromstring(xml)
    # Qualquer falha de leitura é arquivo inválido, e a mensagem precisa ser uma só.
    except Exception as exc:
        raise NotaInvalidaError("O arquivo não é um XML válido.") from exc

    # Aceita nfeProc (nota autorizada) e NFe solta.
    inf = raiz.find(".//nfe:infNFe", {"nfe": NAMESPACE})
    if inf is None:
        raise NotaInvalidaError(
            "Não encontrei uma NF-e neste arquivo. Envie o XML da nota, não o DANFE."
        )

    chave = _digitos(inf.get("Id"))
    if chave is None or len(chave) != CHAVE_LENGTH:
        raise NotaInvalidaError("A chave de acesso da nota não está no arquivo ou está incompleta.")

    emitente_cnpj = _digitos(_texto(inf, "nfe:emit/nfe:CNPJ"))
    if emitente_cnpj is None:
        raise NotaInvalidaError("A nota não traz o CNPJ de quem emitiu.")

    itens = tuple(_ler_itens(inf))
    if not itens:
        raise NotaInvalidaError("A nota não tem itens.")

    return NotaLida(
        chave=chave,
        numero=_texto(inf, "nfe:ide/nfe:nNF"),
        serie=_texto(inf, "nfe:ide/nfe:serie"),
        emitente_cnpj=emitente_cnpj,
        emitente_nome=_texto(inf, "nfe:emit/nfe:xNome"),
        emitida_em=_emitida_em(_texto(inf, "nfe:ide/nfe:dhEmi")),
        valor_total=_decimal(inf, "nfe:total/nfe:ICMSTot/nfe:vNF"),
        itens=itens,
    )


def _ler_itens(inf):  # type: ignore[no-untyped-def]
    for posicao, det in enumerate(inf.findall("nfe:det", {"nfe": NAMESPACE}), start=1):
        prod = det.find("nfe:prod", {"nfe": NAMESPACE})
        if prod is None:
            continue

        descricao = _texto(prod, "nfe:xProd")
        codigo = _texto(prod, "nfe:cProd")
        if descricao is None or codigo is None:
            raise NotaInvalidaError(f"O item {posicao} da nota está sem código ou sem descrição.")

        quantidade = _decimal(prod, "nfe:qCom")
        if quantidade <= 0:
            raise NotaInvalidaError(f"O item {posicao} da nota veio com quantidade zero.")

        # O número do item é atributo do det; a posição no arquivo é o reserva.
        numero = det.get("nItem")

        yield ItemLido(
            numero=int(numero) if numero and numero.isdigit() else posicao,
            codigo_fornecedor=codigo,
            descricao=descricao,
            gtin=_gtin(_texto(prod, "nfe:cEAN")),
            ncm=_digitos(_texto(prod, "nfe:NCM")),
            cest=_digitos(_texto(prod, "nfe:CEST")),
            unidade_comercial=_texto(prod, "nfe:uCom"),
            quantidade=quantidade,
            valor_unitario=_decimal(prod, "nfe:vUnCom"),
            valor_total=_decimal(prod, "nfe:vProd"),
        )
