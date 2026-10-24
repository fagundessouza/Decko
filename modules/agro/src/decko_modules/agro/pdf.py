"""Emissão do Planejamento Operacional em PDF.

Reproduz a estrutura do talão de quatro vias usado hoje, seção por seção, para que o
documento impresso possa substituí-lo sem que o operador precise reaprender a lê-lo.

Nenhum campo novo é acrescentado ao formulário. As violações de parâmetro detectadas na
captura meteorológica entram em "Observações", que já existe no talão, em vez de criar uma
coluna que o documento legal não prevê.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from decko_modules.agro.enums import Momento, Periodo
from decko_modules.agro.geo import format_coordinates

PAGE_WIDTH = A4[0] - 24 * mm

LABEL = ParagraphStyle("label", fontName="Helvetica", fontSize=6, leading=7)
VALUE = ParagraphStyle("value", fontName="Helvetica-Bold", fontSize=7.5, leading=9)
SECTION = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=7.5, leading=9, alignment=1)
TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=1)
FOOT = ParagraphStyle("foot", fontName="Helvetica", fontSize=5.5, leading=7, alignment=1)

GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]
)


@dataclass
class ProductLine:
    produto: str
    formulacao: str = ""
    classe_toxicologica: str = ""
    dosagem_ha: Decimal | None = None
    volume_ha: Decimal | None = None
    total_produto: Decimal | None = None
    adjuvante: str = ""


@dataclass
class WeatherCell:
    hora: str = ""
    temperatura: str = ""
    umidade: str = ""
    vento: str = ""


@dataclass
class WeatherBlock:
    data: date
    # Chaveado por (periodo, momento).
    cells: dict[tuple[Periodo, Momento], WeatherCell] = field(default_factory=dict)


@dataclass
class SignatureLine:
    titulo: str
    rotulo: str
    nome: str = ""
    registro: str = ""


@dataclass
class PlanDocument:
    """Tudo o que o documento imprime, já resolvido.

    O gerador não consulta banco: recebe dados prontos e devolve bytes. Isso o torna
    testável sem infraestrutura e impede que a emissão dispare consultas inesperadas.
    """

    numero: int
    empresa_nome: str
    empresa_cnpj: str = ""
    registro_mapa: str = ""
    crea: str = ""
    cda: str = ""
    inscricao_estadual: str = ""
    inscricao_municipal: str = ""
    rodape: str = ""

    contratante: str = ""
    contratante_documento: str = ""
    propriedade: str = ""
    municipio: str = ""
    uf: str = ""
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    cotacao: str = ""
    cultura: str = ""
    tipos_aplicacao: str = ""
    area_ha: Decimal | None = None

    produtos: list[ProductLine] = field(default_factory=list)
    receituario_numero: str = ""
    receituario_emitido_em: date | None = None

    equipamento_tipo: str = ""
    equipamento_modelo: str = ""
    equipamento_bico_tipo: str = ""
    equipamento_bico_angulo: str = ""
    temperatura_maxima: Decimal | None = None
    umidade_minima: Decimal | None = None
    largura_faixa: Decimal | None = None
    altura_voo: Decimal | None = None
    velocidade_vento_max: Decimal | None = None

    aeronave_prefixo: str = ""
    manutencao_inicial: dict[str, Decimal | None] = field(default_factory=dict)
    manutencao_final: dict[str, Decimal | None] = field(default_factory=dict)
    tempo_servico: Decimal | None = None
    ha_aplicado: Decimal | None = None
    emitiu_dgps: bool | None = None
    termo_higrometro: str = ""

    blocos_meteorologicos: list[WeatherBlock] = field(default_factory=list)
    observacoes: str = ""
    alertas: list[str] = field(default_factory=list)
    assinaturas: list[SignatureLine] = field(default_factory=list)


def _n(value: Decimal | None, casas: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{casas}f}".replace(".", ",")


def _d(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _p(text: str, style: ParagraphStyle = VALUE) -> Paragraph:
    return Paragraph(text or "", style)


def _labelled(label: str, value: str) -> Paragraph:
    return Paragraph(f'<font size="6">{label}</font><br/><b>{value or "&nbsp;"}</b>', LABEL)


def _section(title: str) -> Table:
    table = Table([[Paragraph(title, SECTION)]], colWidths=[PAGE_WIDTH])
    table.setStyle(
        TableStyle(
            [
                *GRID.getCommands(),
                ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.90, 0.90, 0.90)),
            ]
        )
    )
    return table


def _header(doc: PlanDocument) -> list:
    identificacao = Table(
        [
            [
                _p(doc.empresa_nome, TITLE),
                Paragraph("PLANEJAMENTO OPERACIONAL", SECTION),
                _labelled("Nº", str(doc.numero)),
            ]
        ],
        colWidths=[PAGE_WIDTH * 0.35, PAGE_WIDTH * 0.45, PAGE_WIDTH * 0.20],
    )
    identificacao.setStyle(GRID)

    registros = Table(
        [
            [
                _labelled("Nº Registro MAPA", doc.registro_mapa),
                _labelled("CREA", doc.crea),
                _labelled("CDA", doc.cda),
            ],
            [
                _labelled("CNPJ", doc.empresa_cnpj),
                _labelled("Insc. Estadual", doc.inscricao_estadual),
                _labelled("Insc. Municipal", doc.inscricao_municipal),
            ],
        ],
        colWidths=[PAGE_WIDTH / 3] * 3,
    )
    registros.setStyle(GRID)

    contratante = Table(
        [
            [
                _labelled("Contratante", doc.contratante),
                _labelled("CNPJ/CPF", doc.contratante_documento),
            ],
            [
                _labelled("Propriedade", doc.propriedade),
                _labelled("Município / UF", f"{doc.municipio} / {doc.uf}".strip(" /")),
            ],
            [
                _labelled(
                    "Coordenadas da Área",
                    format_coordinates(doc.latitude, doc.longitude),
                ),
                _labelled("Cotação", doc.cotacao),
            ],
        ],
        colWidths=[PAGE_WIDTH * 0.62, PAGE_WIDTH * 0.38],
    )
    contratante.setStyle(GRID)

    return [identificacao, registros, contratante]


def _application(doc: PlanDocument) -> list:
    guia = Table(
        [
            [
                _labelled("Cultura", doc.cultura),
                _labelled("Tipo de aplicação", doc.tipos_aplicacao),
                _labelled("Tamanho da Área (ha)", _n(doc.area_ha, 4)),
            ]
        ],
        colWidths=[PAGE_WIDTH * 0.34, PAGE_WIDTH * 0.42, PAGE_WIDTH * 0.24],
    )
    guia.setStyle(GRID)

    cabecalho = [
        "Produto",
        "Formulação",
        "Classe Toxicológica",
        "Dosagem/Ha",
        "Volume/Ha",
        "Total de Produto",
        "Adjuvante",
    ]
    linhas: list[list] = [[Paragraph(c, LABEL) for c in cabecalho]]
    for item in doc.produtos:
        linhas.append(
            [
                _p(item.produto),
                _p(item.formulacao),
                _p(item.classe_toxicologica),
                _p(_n(item.dosagem_ha, 4)),
                _p(_n(item.volume_ha, 4)),
                _p(_n(item.total_produto, 4)),
                _p(item.adjuvante),
            ]
        )
    # O talão tem linhas em branco para preenchimento à mão; mantidas para o documento
    # continuar utilizável quando a emissão for parcial.
    for _ in range(max(0, 4 - len(doc.produtos))):
        linhas.append([_p("")] * 7)

    larguras = [0.22, 0.14, 0.14, 0.12, 0.12, 0.13, 0.13]
    produtos = Table(linhas, colWidths=[PAGE_WIDTH * w for w in larguras])
    produtos.setStyle(GRID)

    receituario = Table(
        [
            [
                _labelled("Receituário Agronômico Nº", doc.receituario_numero),
                _labelled("Emitido em", _d(doc.receituario_emitido_em)),
                Paragraph("Precauções de uso: vide Receituário Agronômico", LABEL),
            ]
        ],
        colWidths=[PAGE_WIDTH * 0.30, PAGE_WIDTH * 0.22, PAGE_WIDTH * 0.48],
    )
    receituario.setStyle(GRID)

    return [guia, produtos, receituario]


def _equipment(doc: PlanDocument) -> list:
    equipamento = Table(
        [
            [
                _labelled("Equipamento", doc.equipamento_tipo),
                _labelled("Modelo", doc.equipamento_modelo),
                _labelled("Tipo de bico", doc.equipamento_bico_tipo),
                _labelled("Ângulo", doc.equipamento_bico_angulo),
            ],
            [
                _labelled("Temperatura Máxima (°C)", _n(doc.temperatura_maxima)),
                _labelled("Umidade Relativa Mínima (%)", _n(doc.umidade_minima)),
                _labelled("Largura da Faixa (m)", _n(doc.largura_faixa)),
                _labelled("Altura do Voo (m)", _n(doc.altura_voo)),
            ],
            [
                _labelled("Velocidade do Vento (km/h)", _n(doc.velocidade_vento_max)),
                _labelled("Prefixo da Aeronave", doc.aeronave_prefixo),
                _labelled("Tempo de Serviço", _n(doc.tempo_servico)),
                _labelled("Ha Aplicado", _n(doc.ha_aplicado, 4)),
            ],
        ],
        colWidths=[PAGE_WIDTH / 4] * 4,
    )
    equipamento.setStyle(GRID)

    colunas = ["voo", "translado_ida", "operacao", "translado_volta", "total"]
    rotulos = ["Voo", "Translado Ida", "Operação", "Translado Volta", "Total"]
    manutencao = Table(
        [
            [Paragraph("Controle de Manutenção (Horas x Voo)", LABEL)]
            + [Paragraph(r, LABEL) for r in rotulos],
            [_p("Inicial")] + [_p(_n(doc.manutencao_inicial.get(c))) for c in colunas],
            [_p("Final")] + [_p(_n(doc.manutencao_final.get(c))) for c in colunas],
        ],
        colWidths=[PAGE_WIDTH * 0.30] + [PAGE_WIDTH * 0.14] * 5,
    )
    manutencao.setStyle(GRID)

    dgps = {True: "Sim", False: "Não", None: ""}[doc.emitiu_dgps]
    complemento = Table(
        [
            [
                _labelled("Emitiu Relatório DGPS?", dgps),
                _labelled("Termo Higrômetro Utilizado", doc.termo_higrometro),
            ]
        ],
        colWidths=[PAGE_WIDTH * 0.32, PAGE_WIDTH * 0.68],
    )
    complemento.setStyle(GRID)

    return [equipamento, manutencao, complemento]


def _weather(doc: PlanDocument) -> list:
    elementos: list = [_section("Condições Meteorológicas na Aplicação")]

    cabecalho = Table(
        [
            [
                Paragraph("Data", LABEL),
                Paragraph("Período", LABEL),
                Paragraph("Matutino — Início", LABEL),
                Paragraph("Matutino — Final", LABEL),
                Paragraph("Vespertino — Início", LABEL),
                Paragraph("Vespertino — Final", LABEL),
            ]
        ],
        colWidths=[PAGE_WIDTH * 0.14, PAGE_WIDTH * 0.22] + [PAGE_WIDTH * 0.16] * 4,
    )
    cabecalho.setStyle(GRID)
    elementos.append(cabecalho)

    campos = [
        ("Hora (hh:mm)", "hora"),
        ("Temperatura (°C)", "temperatura"),
        ("Umidade Relativa (%)", "umidade"),
        ("Vel. do Vento (km/h)", "vento"),
    ]
    # Três blocos é o que o talão imprime; havendo mais datas, o documento cresce em vez
    # de descartar leitura, porque descartar apagaria registro com efeito legal.
    blocos = doc.blocos_meteorologicos or [WeatherBlock(data=date.today())]

    for bloco in blocos:
        linhas = []
        for indice, (rotulo, atributo) in enumerate(campos):
            celulas = [
                getattr(
                    bloco.cells.get((periodo, momento), WeatherCell()),
                    atributo,
                )
                for periodo in (Periodo.MATUTINO, Periodo.VESPERTINO)
                for momento in (Momento.INICIO, Momento.FINAL)
            ]
            linhas.append(
                [_p(_d(bloco.data) if indice == 0 else ""), Paragraph(rotulo, LABEL)]
                + [_p(valor) for valor in celulas]
            )

        tabela = Table(
            linhas, colWidths=[PAGE_WIDTH * 0.14, PAGE_WIDTH * 0.22] + [PAGE_WIDTH * 0.16] * 4
        )
        tabela.setStyle(GRID)
        elementos.append(KeepTogether(tabela))

    return elementos


def _closing(doc: PlanDocument) -> list:
    corpo = doc.observacoes or ""
    if doc.alertas:
        aviso = "<br/>".join(f"• {a}" for a in doc.alertas)
        corpo = (
            f"{corpo}<br/>" if corpo else ""
        ) + f"<b>Condições fora dos parâmetros planejados:</b><br/>{aviso}"

    observacoes = Table(
        [
            [Paragraph("Observações", LABEL)],
            [Paragraph(corpo or "&nbsp;", VALUE)],
        ],
        colWidths=[PAGE_WIDTH],
        rowHeights=[12, 46],
    )
    observacoes.setStyle(GRID)

    padrao = [
        SignatureLine("Eng. Agrônomo", "Nome / Assinatura / CREA"),
        SignatureLine("Piloto Agrícola", "Nome / Assinatura / CANAC"),
        SignatureLine("Téc. Agrícola Executor", "Nome / Assinatura / CREA"),
        SignatureLine("Proprietário ou Preposto", "Nome completo / Assinatura"),
    ]
    preenchidas = {a.titulo: a for a in doc.assinaturas}
    linhas = [preenchidas.get(p.titulo, p) for p in padrao]

    assinaturas = Table(
        [
            [Paragraph(linha.titulo, SECTION) for linha in linhas],
            [_p(f"{linha.nome}<br/>{linha.registro}".strip("<br/>")) for linha in linhas],
            [Paragraph(linha.rotulo, LABEL) for linha in linhas],
        ],
        colWidths=[PAGE_WIDTH / 4] * 4,
        rowHeights=[12, 36, 12],
    )
    assinaturas.setStyle(GRID)

    rodape = [
        Paragraph(doc.rodape, FOOT),
        # Travessões reproduzem o rodapé do talão; trocá-los por hífen afastaria o
        # documento do original, que é justamente o que esta emissão precisa substituir.
        Paragraph(
            "1ª Via Branca – Empresa / 2ª Via Rosa – Cliente / "  # noqa: RUF001
            "3ª Via Azul – Piloto / 4ª Via Amarela – Fixa",  # noqa: RUF001
            FOOT,
        ),
    ]

    return [observacoes, Spacer(1, 3), assinaturas, Spacer(1, 4), *rodape]


def render(doc: PlanDocument) -> bytes:
    """Monta o documento e devolve os bytes do PDF."""
    buffer = BytesIO()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Planejamento Operacional nº {doc.numero}",
        author=doc.empresa_nome,
    )

    story: list = []
    story += _header(doc)
    story.append(_section("Guia de Aplicação"))
    story += _application(doc)
    story.append(_section("Equipamento, Parâmetros e Aeronave"))
    story += _equipment(doc)
    story += _weather(doc)
    story.append(Spacer(1, 3))
    story += _closing(doc)

    template.build(story)
    return buffer.getvalue()
