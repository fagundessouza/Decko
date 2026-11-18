"""Leitura da planilha de voos exportada pelo DJI SmartFarm.

O requisito é do Nathan, em 13/11/2026: *"seria top se desse para conectar com esse app,
assim os relatórios de voo já ficariam com os registros tudo lá. Com horário de início,
fim, área aplicada."* Não existe API pública do SmartFarm — a apuração está na seção 7 do
``docs/discovery/agro-planejamento-operacional.md``. O que existe é este arquivo, que ele
já consegue exportar, e é dele que se tira o dado.

O que esta leitura **não** faz é decidir. Ela devolve o que entendeu do arquivo; casar com
o planejamento e gravar é outro passo, com confirmação de quem operou — a mesma forma da
entrada por nota do módulo ``compras`` (ADR 0009) e da importação do croqui.

## A unidade da área, que é a armadilha deste arquivo

A coluna de área **não traz unidade no cabeçalho**. Quem traz é a coluna vizinha:
``Usage Per Mu(L/Kg/Mu)``. O arquivo de 17/11/2026 está em **mu** — unidade chinesa de
1/15 de hectare — porque é assim que a conta do aplicativo está configurada.

Isso não é detalhe: ler 482,94 mu como hectare põe no relatório do MAPA uma área **quinze
vezes maior** do que a aplicada, com a dosagem por hectare caindo na mesma proporção. O
relatório mensal é obrigatório e vai ao SIPEAGRO até o dia 15 do mês seguinte
(Portaria MAPA 298/2021, art. 11 e art. 19, I); divergência ali é o que custa dinheiro.

Por isso a unidade é **lida do cabeçalho**, nunca suposta, e cabeçalho que não se reconhece
faz a leitura ser recusada em vez de convertida por palpite.

## O horário não tem fuso

A coluna de voo traz ``2026-08-15 19:47:45-19:48:09``, sem deslocamento. A leitura devolve
o instante como está no arquivo, sem converter, e avisa. Quem resolve isso é quem conhece a
operação: o relatório é em horário local, e errar o fuso em três horas desloca também a
leitura meteorológica que confronta aquele horário.

**Segurança.** O arquivo vem de fora. O ``.xlsx`` é um zip de XML, e o parser padrão aceita
entidade externa — então o XML é lido com ``defusedxml``, como o da NF-e.
"""

import csv
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO

from defusedxml import ElementTree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: Um mu é 1/15 de hectare, por definição.
MU_EM_HA = Decimal(1) / Decimal(15)

#: Teto de linhas. Planilha de voo de um mês tem dezenas; milhares significam outro arquivo.
TETO_DE_LINHAS = 20_000


class PlanilhaInvalidaError(ValueError):
    """O arquivo não é uma planilha de voos legível. A mensagem vai para a tela."""


@dataclass(frozen=True)
class VooLido:
    """Um voo, como a planilha o registra. Um voo é uma bateria, não uma aplicação."""

    comecou_em: datetime
    terminou_em: datetime
    duracao: timedelta
    aeronave: str
    # O número de série do equipamento, que é o que casa com a aeronave cadastrada. O
    # "Aircraft name" é apelido que o operador escolhe ("Valkyria"), e apelido não
    # identifica ARP para o MAPA.
    equipamento_serie: str | None
    piloto: str | None
    talhao: str | None
    plot_id: str | None
    #: Na unidade do arquivo, sem conversão. A conversão é da aplicação.
    area: Decimal
    volume_l: Decimal
    largura_faixa_m: Decimal | None
    altura_voo_m: Decimal | None
    local: str | None

    @property
    def aplicou(self) -> bool:
        """Voo com talhão e área é aplicação; o resto é translado, teste ou decolagem.

        Sem esta separação, o relatório ganharia linha de voo que não pulverizou nada —
        e a contagem de aplicações do mês ficaria maior do que a operação.
        """
        return self.plot_id is not None and self.area > 0


@dataclass(frozen=True)
class AplicacaoLida:
    """Os voos de um mesmo talhão no mesmo dia, somados.

    É a resposta da pergunta 2 da seção 7.4 do discovery — *"um voo é um planejamento?"*.
    No arquivo, não: uma aplicação de 32 ha aparece como cinco voos, um por bateria, todos
    com o mesmo ``Plot ID``. O relatório é por aplicação, então é assim que se junta.
    """

    plot_id: str
    talhao: str | None
    dia: date
    comecou_em: datetime
    terminou_em: datetime
    #: Já em hectare, convertida da unidade do arquivo.
    area_ha: Decimal
    volume_l: Decimal
    #: Horas de execução, que a Portaria 298/2021 exige no relatório mensal (art. 11, III).
    duracao: timedelta
    voos: int
    aeronave: str
    equipamento_serie: str | None
    piloto: str | None
    local: str | None
    #: Só quando todos os voos concordam. Divergência entre voos não é média, é intervalo.
    largura_faixa_m: Decimal | None
    altura_voo_m: Decimal | None
    #: O menor e o maior valor dos voos, sempre que houver algum.
    #:
    #: A altura varia de voo para voo — 5,8 m aqui, 6,3 m ali — porque é o que o
    #: equipamento voou, não o que alguém planejou. Média poria no documento um número que
    #: não aconteceu em voo nenhum; o intervalo é o que de fato aconteceu, e quem preenche
    #: o talão decide o que declarar.
    largura_faixa_intervalo: tuple[Decimal, Decimal] | None
    altura_voo_intervalo: tuple[Decimal, Decimal] | None

    @property
    def volume_por_ha(self) -> Decimal | None:
        if self.area_ha <= 0:
            return None
        return (self.volume_l / self.area_ha).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class HorasDoEquipamento:
    """O que um equipamento voou no arquivo, para o horímetro e a manutenção.

    Separa o que pulverizou do que não pulverizou **sem descartar nada**: translado,
    calibração e decolagem abortada desgastam motor, hélice e bateria igual, e é por isso
    que a revisão vence. O relatório do MAPA leva só a aplicação; a manutenção leva tudo.
    """

    equipamento_serie: str | None
    aeronave: str
    voos: int
    duracao_total: timedelta
    duracao_aplicando: timedelta
    duracao_auxiliar: timedelta


@dataclass(frozen=True)
class Leitura:
    #: Como o arquivo mede área: "mu", "ha" ou "acre". Lida do cabeçalho.
    unidade_de_area: str
    aplicacoes: list[AplicacaoLida]
    #: Voos que não pulverizaram: translado, calibração, teste, decolagem abortada.
    #:
    #: Eles **não** são descartados. Ficam aqui inteiros porque alimentam o horímetro da
    #: frota — e porque sumir com linha de um arquivo que o operador está conferindo é a
    #: melhor forma de ele deixar de confiar no que o sistema leu.
    voos_auxiliares: list[VooLido]
    #: Por equipamento: o que voou, e quanto disso foi aplicando.
    horimetro: list[HorasDoEquipamento]
    #: O que quem for confirmar precisa saber antes de confirmar.
    avisos: list[str]

    @property
    def voos_sem_aplicacao(self) -> int:
        return len(self.voos_auxiliares)


# ------------------------------------------------------------------ o arquivo

#: As colunas que este leitor conhece, na ordem em que o SmartFarm as exporta.
COLUNAS = {
    "flight time": "voo",
    "location": "local",
    "aircraft name": "aeronave",
    "task type": "tarefa",
    "sprayed area": "area",
    "total amount(l/kg)": "volume",
    "flight duration(min:sec)": "duracao",
    "crop": "cultura",
    "pliot name": "piloto",  # a grafia é do arquivo, não daqui
    "pilot name": "piloto",
    "team name": "equipe",
    "field name": "talhao",
    "serial number": "serie_do_registro",
    "height": "altura",
    "row spacing": "largura",
    "body code": "equipamento",
    "plot id": "plot_id",
}

#: O cabeçalho de consumo é o único lugar do arquivo que diz a unidade da área.
UNIDADES = {"mu": "mu", "ha": "ha", "hectare": "ha", "acre": "acre", "mou": "mu"}


def _celulas(zf: zipfile.ZipFile) -> list[list[str]]:
    """As linhas da primeira aba, como texto, sem colunas vazias à direita."""
    try:
        aba = zf.read("xl/worksheets/sheet1.xml")
    except KeyError as exc:
        raise PlanilhaInvalidaError("Este arquivo não parece ser uma planilha.") from exc

    compartilhadas: list[str] = []
    try:
        raiz_textos = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in raiz_textos.findall(f"{NS}si"):
            compartilhadas.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    except KeyError:
        pass

    raiz = ElementTree.fromstring(aba)
    linhas: list[list[str]] = []
    for linha in raiz.iter(f"{NS}row"):
        valores: dict[int, str] = {}
        for celula in linha.findall(f"{NS}c"):
            indice = _indice_da_coluna(celula.get("r") or "")
            valores[indice] = _texto_da_celula(celula, compartilhadas)
        if valores:
            largura = max(valores) + 1
            linhas.append([valores.get(i, "") for i in range(largura)])
        if len(linhas) > TETO_DE_LINHAS:
            raise PlanilhaInvalidaError(
                "Esta planilha tem linhas demais para ser um relatório de voo."
            )
    return linhas


def _texto_da_celula(celula, compartilhadas: list[str]) -> str:  # type: ignore[no-untyped-def]
    tipo = celula.get("t")
    if tipo == "s":
        valor = celula.find(f"{NS}v")
        if valor is None or valor.text is None:
            return ""
        indice = int(valor.text)
        return compartilhadas[indice].strip() if indice < len(compartilhadas) else ""
    if tipo == "inlineStr":
        inline = celula.find(f"{NS}is")
        if inline is None:
            return ""
        return "".join(t.text or "" for t in inline.iter(f"{NS}t")).strip()
    valor = celula.find(f"{NS}v")
    return (valor.text or "").strip() if valor is not None else ""


def _indice_da_coluna(referencia: str) -> int:
    letras = "".join(c for c in referencia if c.isalpha())
    indice = 0
    for letra in letras:
        indice = indice * 26 + (ord(letra.upper()) - 64)
    return max(indice - 1, 0)


def _unidade_da_area(cabecalho: list[str]) -> str:
    """A unidade sai do cabeçalho de consumo — "Usage Per Mu(L/Kg/Mu)".

    Recusar é de propósito. Supor hectare num arquivo em mu multiplica a área por quinze
    no relatório do MAPA, e isso não dá erro em nenhuma tela: dá um número errado com cara
    de certo.
    """
    for texto in cabecalho:
        bruto = texto.strip().lower()
        if not bruto.startswith("usage per"):
            continue
        palavra = bruto.removeprefix("usage per").split("(")[0].strip()
        if palavra in UNIDADES:
            return UNIDADES[palavra]
        raise PlanilhaInvalidaError(
            f"Não reconheço a unidade de área desta planilha ({texto}). "
            "Sem saber a unidade, a área aplicada não pode ser importada."
        )
    raise PlanilhaInvalidaError(
        "Esta planilha não diz em que unidade a área está medida. O SmartFarm põe isso na "
        "coluna de consumo por área; exporte de novo incluindo essa coluna."
    )


def _mapa_das_colunas(cabecalho: list[str]) -> dict[str, int]:
    achadas: dict[str, int] = {}
    for indice, texto in enumerate(cabecalho):
        nome = COLUNAS.get(texto.strip().lower())
        if nome is not None and nome not in achadas:
            achadas[nome] = indice

    faltando = {"voo", "area", "volume", "duracao"} - achadas.keys()
    if faltando:
        raise PlanilhaInvalidaError(
            "Esta planilha não tem as colunas de voo do SmartFarm "
            f"(faltam: {', '.join(sorted(faltando))})."
        )
    return achadas


def _decimal(bruto: str) -> Decimal | None:
    if not bruto:
        return None
    try:
        return Decimal(bruto.replace(",", "."))
    except InvalidOperation:
        return None


def _instantes(bruto: str) -> tuple[datetime, datetime]:
    """Lê "2026-08-15 19:47:45-19:48:09" como dois instantes, sem fuso.

    O segundo horário não repete a data. Voo que termina antes de começar atravessou a
    meia-noite, e aí o fim é do dia seguinte.
    """
    try:
        dia, horas = bruto.split(" ", 1)
        inicio_texto, fim_texto = horas.split("-", 1)
        comecou = datetime.fromisoformat(f"{dia} {inicio_texto.strip()}")
        terminou = datetime.fromisoformat(f"{dia} {fim_texto.strip()}")
    except ValueError as exc:
        raise PlanilhaInvalidaError(
            f"Não consegui ler o horário do voo nesta linha: {bruto!r}."
        ) from exc

    if terminou < comecou:
        terminou += timedelta(days=1)
    return comecou, terminou


def _duracao(bruto: str) -> timedelta:
    """ "07:34" é minuto e segundo, como o cabeçalho diz — não hora e minuto."""
    partes = bruto.split(":")
    try:
        if len(partes) == 2:
            return timedelta(minutes=int(partes[0]), seconds=int(partes[1]))
        if len(partes) == 3:
            return timedelta(hours=int(partes[0]), minutes=int(partes[1]), seconds=int(partes[2]))
    except ValueError:
        pass
    raise PlanilhaInvalidaError(f"Não consegui ler a duração do voo: {bruto!r}.")


def _em_hectare(area: Decimal, unidade: str) -> Decimal:
    if unidade == "mu":
        return (area * MU_EM_HA).quantize(Decimal("0.0001"))
    if unidade == "acre":
        return (area * Decimal("0.404686")).quantize(Decimal("0.0001"))
    return area.quantize(Decimal("0.0001"))


def _voo(linha: list[str], colunas: dict[str, int]) -> VooLido:
    def campo(nome: str) -> str:
        indice = colunas.get(nome)
        if indice is None or indice >= len(linha):
            return ""
        return linha[indice]

    comecou, terminou = _instantes(campo("voo"))
    return VooLido(
        comecou_em=comecou,
        terminou_em=terminou,
        duracao=_duracao(campo("duracao")),
        aeronave=campo("aeronave"),
        equipamento_serie=campo("equipamento") or None,
        piloto=campo("piloto") or None,
        talhao=campo("talhao") or None,
        plot_id=campo("plot_id") or None,
        area=_decimal(campo("area")) or Decimal(0),
        volume_l=_decimal(campo("volume")) or Decimal(0),
        largura_faixa_m=_decimal(campo("largura")) or None,
        altura_voo_m=_decimal(campo("altura")) or None,
        local=campo("local") or None,
    )


def _agrupar(voos: list[VooLido], unidade: str) -> tuple[list[AplicacaoLida], list[str]]:
    por_aplicacao: dict[tuple[str, date], list[VooLido]] = {}
    for voo in voos:
        # A segunda condição repete o que `aplicou` garante; ela existe para o verificador
        # de tipo saber que o `plot_id` não é nulo, sem `assert` em código de aplicação.
        if not voo.aplicou or voo.plot_id is None:
            continue
        por_aplicacao.setdefault((voo.plot_id, voo.comecou_em.date()), []).append(voo)

    avisos: list[str] = []
    aplicacoes: list[AplicacaoLida] = []
    for (plot_id, dia), do_grupo in sorted(por_aplicacao.items(), key=lambda item: item[0][1]):
        ordenados = sorted(do_grupo, key=lambda voo: voo.comecou_em)
        aeronaves = {voo.aeronave for voo in ordenados if voo.aeronave}
        if len(aeronaves) > 1:
            avisos.append(
                f"Em {dia:%d/%m/%Y}, o talhão {ordenados[0].talhao or plot_id} teve voos de "
                f"mais de uma aeronave ({', '.join(sorted(aeronaves))}). Confira antes de usar."
            )

        aplicacoes.append(
            AplicacaoLida(
                plot_id=plot_id,
                talhao=next((voo.talhao for voo in ordenados if voo.talhao), None),
                dia=dia,
                comecou_em=ordenados[0].comecou_em,
                terminou_em=max(voo.terminou_em for voo in ordenados),
                area_ha=_em_hectare(sum((voo.area for voo in ordenados), Decimal(0)), unidade),
                volume_l=sum((voo.volume_l for voo in ordenados), Decimal(0)),
                duracao=sum((voo.duracao for voo in ordenados), timedelta()),
                voos=len(ordenados),
                aeronave=ordenados[0].aeronave,
                equipamento_serie=next(
                    (voo.equipamento_serie for voo in ordenados if voo.equipamento_serie), None
                ),
                piloto=next((voo.piloto for voo in ordenados if voo.piloto), None),
                local=next((voo.local for voo in ordenados if voo.local), None),
                largura_faixa_m=_concordam(voo.largura_faixa_m for voo in ordenados),
                altura_voo_m=_concordam(voo.altura_voo_m for voo in ordenados),
                largura_faixa_intervalo=_intervalo(voo.largura_faixa_m for voo in ordenados),
                altura_voo_intervalo=_intervalo(voo.altura_voo_m for voo in ordenados),
            )
        )
    return aplicacoes, avisos


def _intervalo(valores: Iterable[Decimal | None]) -> tuple[Decimal, Decimal] | None:
    """O menor e o maior valor dos voos, para a tela mostrar o que variou."""
    presentes = [valor for valor in valores if valor is not None]
    return (min(presentes), max(presentes)) if presentes else None


def _concordam(valores: Iterable[Decimal | None]) -> Decimal | None:
    """O valor quando todos os voos dizem o mesmo; nada quando divergem.

    Média de largura de faixa não existe no documento: ou a aplicação foi feita com aquela
    faixa, ou alguém mudou o equipamento no meio e isso precisa aparecer.
    """
    distintos = {valor for valor in valores if valor is not None}
    return distintos.pop() if len(distintos) == 1 else None


#: Todo zip começa assim, e um .xlsx é um zip. É como se sabe qual dos dois formatos veio.
ASSINATURA_ZIP = b"PK"


def _linhas_do_csv(conteudo: bytes) -> list[list[str]]:
    """O mesmo conteúdo em texto separado por vírgula ou ponto e vírgula.

    O separador é descoberto pela primeira linha, e não suposto: planilha salva em
    computador com configuração brasileira sai com ponto e vírgula, e ler uma com a regra
    da outra devolveria uma coluna só — o que viraria "faltam as colunas de voo" numa tela
    de quem não errou nada.
    """
    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 aceita qualquer byte
        raise PlanilhaInvalidaError("Não consegui ler este arquivo como texto.")

    primeira = texto.splitlines()[0] if texto.splitlines() else ""
    separador = ";" if primeira.count(";") > primeira.count(",") else ","
    return [
        [celula.strip() for celula in linha]
        for linha in csv.reader(StringIO(texto), delimiter=separador)
        if any(celula.strip() for celula in linha)
    ]


def ler(conteudo: bytes) -> Leitura:
    """Lê o registro de voo — `.xlsx` ou `.csv` — e devolve as aplicações que ele descreve.

    Não grava nada e não decide nada: o casamento com o planejamento e a confirmação são
    de quem operou.
    """
    if conteudo.startswith(ASSINATURA_ZIP):
        with zipfile.ZipFile(BytesIO(conteudo)) as zf:
            linhas = _celulas(zf)
    elif b"," in conteudo[:4096] or b";" in conteudo[:4096]:
        linhas = _linhas_do_csv(conteudo)
    else:
        raise PlanilhaInvalidaError(
            "Este arquivo não é uma planilha nem um CSV. Exporte os voos do SmartFarm "
            "em .xlsx ou .csv."
        )

    if not linhas:
        raise PlanilhaInvalidaError("Esta planilha está vazia.")

    cabecalho = linhas[0]
    colunas = _mapa_das_colunas(cabecalho)
    unidade = _unidade_da_area(cabecalho)

    voos = [_voo(linha, colunas) for linha in linhas[1:] if any(celula for celula in linha)]
    if not voos:
        raise PlanilhaInvalidaError("Esta planilha tem o cabeçalho de voos, mas nenhum voo.")

    aplicacoes, avisos = _agrupar(voos, unidade)
    auxiliares = [voo for voo in voos if not voo.aplicou]
    sem_aplicacao = len(auxiliares)

    if unidade != "ha":
        avisos.append(
            f"A área desta planilha está em {unidade}, e foi convertida para hectare "
            f"({len(aplicacoes)} aplicação(ões)). Confira um valor antes de usar no relatório."
        )
    avisos.append(
        "Os horários da planilha não trazem fuso. Confirme se são do horário local antes "
        "de usá-los no relatório e na conferência do clima."
    )
    if sem_aplicacao:
        avisos.append(
            f"{sem_aplicacao} voo(s) não pulverizaram área: são translado, calibração, "
            "teste ou decolagem abortada. Não entram no relatório do MAPA, e entram no "
            "horímetro da aeronave."
        )
    if not aplicacoes:
        avisos.append("Nenhum voo desta planilha pulverizou área.")

    return Leitura(
        unidade_de_area=unidade,
        aplicacoes=aplicacoes,
        voos_auxiliares=auxiliares,
        horimetro=_horimetro(voos),
        avisos=avisos,
    )


def _horimetro(voos: list[VooLido]) -> list[HorasDoEquipamento]:
    """Soma as horas por equipamento, separando o que aplicou do que não aplicou."""
    por_equipamento: dict[str | None, list[VooLido]] = {}
    for voo in voos:
        por_equipamento.setdefault(voo.equipamento_serie, []).append(voo)

    horas = []
    for serie, do_equipamento in por_equipamento.items():
        aplicando = sum((voo.duracao for voo in do_equipamento if voo.aplicou), timedelta())
        total = sum((voo.duracao for voo in do_equipamento), timedelta())
        horas.append(
            HorasDoEquipamento(
                equipamento_serie=serie,
                aeronave=next((voo.aeronave for voo in do_equipamento if voo.aeronave), ""),
                voos=len(do_equipamento),
                duracao_total=total,
                duracao_aplicando=aplicando,
                duracao_auxiliar=total - aplicando,
            )
        )
    return sorted(horas, key=lambda h: h.equipamento_serie or "")
