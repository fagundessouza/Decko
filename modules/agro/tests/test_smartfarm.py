"""A planilha de voos do SmartFarm, lida.

O requisito é do Nathan, em 13/11/2026 — não redigitar início, fim e área aplicada. A
apuração do caminho está na seção 7 do `docs/discovery/agro-planejamento-operacional.md`:
não existe API pública, existe este arquivo.

**O que estes testes guardam é dinheiro dele.** O relatório mensal é obrigatório e vai ao
SIPEAGRO até o dia 15 do mês seguinte (Portaria MAPA 298/2021, art. 11 e art. 19, I), e a
sanção por irregularidade é multa, suspensão ou cancelamento do registro (Decreto
86.765/1981, art. 30, referido pelo art. 23 da Portaria). Área errada ali não dá erro em
tela nenhuma: dá um número errado com cara de certo.

A armadilha é a unidade. A coluna de área não traz unidade; quem traz é a vizinha,
`Usage Per Mu`. Ler mu como hectare multiplica a área por quinze.

As planilhas daqui são montadas no próprio teste, com a estrutura do arquivo real — zip de
XML, com textos compartilhados, como o SmartFarm exporta. Nenhum dado de cliente entra no
repositório.
"""

import csv
import zipfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO

import pytest

from decko_modules.agro import smartfarm

CABECALHO = [
    "Flight time",
    "Location",
    "Aircraft name",
    "Task Type",
    "Sprayed area",
    "Total Amount(L/Kg)",
    "Usage Per Mu(L/Kg/Mu)",
    "Flight duration(min:sec)",
    "Crop",
    "Pliot Name",
    "Team Name",
    "Field Name",
    "Serial Number",
    "Starting Battery Level",
    "Ending Battery Level",
    "Battery SN",
    "Speed",
    "Height",
    "Row Spacing",
    "Body Code",
    "Plot ID",
]


def _planilha(linhas: list[list[str]]) -> bytes:
    """Monta um .xlsx mínimo, com textos compartilhados como o arquivo real usa."""
    textos: list[str] = []
    indice: dict[str, int] = {}
    for linha in linhas:
        for celula in linha:
            if celula not in indice:
                indice[celula] = len(textos)
                textos.append(celula)

    def coluna(n: int) -> str:
        nome = ""
        n += 1
        while n:
            n, resto = divmod(n - 1, 26)
            nome = chr(65 + resto) + nome
        return nome

    corpo = []
    for numero, linha in enumerate(linhas, start=1):
        celulas = "".join(
            f'<c r="{coluna(i)}{numero}" t="s"><v>{indice[valor]}</v></c>'
            for i, valor in enumerate(linha)
            if valor != ""
        )
        corpo.append(f'<row r="{numero}">{celulas}</row>')

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = f'<worksheet xmlns="{ns}"><sheetData>{"".join(corpo)}</sheetData></worksheet>'
    compartilhados = "".join(
        f"<si><t>{t.replace('&', '&amp;').replace('<', '&lt;')}</t></si>" for t in textos
    )
    shared = (
        f'<sst xmlns="{ns}" count="{len(textos)}" uniqueCount="{len(textos)}">'
        f"{compartilhados}</sst>"
    )
    workbook = (
        f'<workbook xmlns="{ns}"><sheets>'
        '<sheet name="flight record" sheetId="1"/></sheets></workbook>'
    )

    pacote = BytesIO()
    with zipfile.ZipFile(pacote, "w") as zf:
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return pacote.getvalue()


def _voo(
    *,
    quando: str,
    area: str,
    volume: str,
    duracao: str,
    talhao: str = "",
    plot: str = "",
    aeronave: str = "Valkyria",
    largura: str = "",
    altura: str = "",
) -> list[str]:
    linha = [""] * len(CABECALHO)
    linha[0] = quando
    linha[1] = "Piracanjuba, Goias, Brazil"
    linha[2] = aeronave
    linha[3] = "Spraying"
    linha[4] = area
    linha[5] = volume
    linha[6] = ""  # a conta por área é do aplicativo; o leitor não usa
    linha[7] = duracao
    linha[8] = "other"
    linha[9] = "Piloto de Teste"
    linha[11] = talhao
    linha[17] = altura
    linha[18] = largura
    linha[19] = "B26WN5P0025A3T"
    linha[20] = plot
    return linha


# ----------------------------------------------------------------- a unidade da área


def test_a_area_em_mu_vira_hectare() -> None:
    """Um mu é 1/15 de hectare. Quinze mu são um hectare, e é esta conta que paga a multa.

    Os números são os de uma aplicação real de referência: cinco voos somando 482,94 mu,
    que são 32,20 ha. Lidos como hectare, o relatório diria 482,94 ha — quinze vezes a
    área aplicada, com a dosagem por hectare caindo na mesma proporção.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="110.11",
                volume="66.28",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="372.83",
                volume="224.06",
                duracao="25:00",
                talhao="Milho 1",
                plot="plot-a",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert leitura.unidade_de_area == "mu"
    assert len(leitura.aplicacoes) == 1
    assert leitura.aplicacoes[0].area_ha == Decimal("32.1960")
    assert leitura.aplicacoes[0].volume_l == Decimal("290.34")
    # Nove litros por hectare é dose de drone; seiscentos mililitros não é de nada.
    assert leitura.aplicacoes[0].volume_por_ha == Decimal("9.02")


def test_planilha_em_hectare_nao_e_convertida() -> None:
    """A conta do aplicativo pode estar configurada em hectare, e aí não se mexe no número."""
    cabecalho = ["Usage Per Ha(L/Kg/ha)" if c.startswith("Usage Per") else c for c in CABECALHO]
    arquivo = _planilha(
        [
            cabecalho,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="32.20",
                volume="290.34",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert leitura.unidade_de_area == "ha"
    assert leitura.aplicacoes[0].area_ha == Decimal("32.2000")


def test_sem_saber_a_unidade_a_leitura_e_recusada() -> None:
    """Recusar é melhor do que supor: supor hectare num arquivo em mu erra por quinze.

    A recusa é a única saída honesta — não existe jeito de deduzir a unidade do número.
    """
    cabecalho = [c for c in CABECALHO if not c.startswith("Usage Per")]
    arquivo = _planilha(
        [
            cabecalho,
            [
                "2026-08-15 18:51:36-18:58:23",
                "",
                "Valkyria",
                "Spraying",
                "110.11",
                "66.28",
                "06:47",
            ],
        ]
    )

    with pytest.raises(smartfarm.PlanilhaInvalidaError, match="unidade"):
        smartfarm.ler(arquivo)


def test_unidade_desconhecida_tambem_e_recusada() -> None:
    cabecalho = [
        "Usage Per Alqueire(L/Kg/alq)" if c.startswith("Usage Per") else c for c in CABECALHO
    ]
    arquivo = _planilha(
        [
            cabecalho,
            _voo(quando="2026-08-15 10:00:00-10:05:00", area="1", volume="1", duracao="05:00"),
        ]
    )

    with pytest.raises(smartfarm.PlanilhaInvalidaError, match="unidade"):
        smartfarm.ler(arquivo)


# ----------------------------------------------------------------- um voo não é uma aplicação


def test_os_voos_do_mesmo_talhao_no_mesmo_dia_sao_uma_aplicacao() -> None:
    """É a resposta da pergunta 2 da seção 7.4 do discovery.

    Uma aplicação de trinta hectares sai do aplicativo como cinco voos, um por bateria,
    todos com o mesmo `Plot ID`. O relatório é por aplicação: tratá-los como cinco
    aplicações multiplicaria por cinco a contagem do mês.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="150",
                volume="60",
                duracao="07:41",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(
                quando="2026-08-15 19:39:08-19:43:08",
                area="150",
                volume="60",
                duracao="04:00",
                talhao="Milho 1",
                plot="plot-a",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert len(leitura.aplicacoes) == 1
    aplicacao = leitura.aplicacoes[0]
    assert aplicacao.voos == 3
    # Da primeira decolagem ao último pouso, e as horas de execução somadas: é o que a
    # Portaria 298/2021 pede no relatório mensal (art. 11, III).
    assert aplicacao.comecou_em.strftime("%H:%M") == "18:51"
    assert aplicacao.terminou_em.strftime("%H:%M") == "19:43"
    assert aplicacao.duracao == timedelta(minutes=18, seconds=28)


def test_talhoes_diferentes_sao_aplicacoes_diferentes() -> None:
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="150",
                volume="60",
                duracao="07:41",
                talhao="Soja 2",
                plot="plot-b",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert {a.talhao for a in leitura.aplicacoes} == {"Milho 1", "Soja 2"}


def test_o_mesmo_talhao_em_dois_dias_sao_duas_aplicacoes() -> None:
    """Duas passadas no mesmo talhão são dois serviços, e dois registros no relatório."""
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-07 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert len(leitura.aplicacoes) == 2


def test_voo_sem_area_fica_de_fora_e_e_contado() -> None:
    """Translado, teste e decolagem abortada aparecem na planilha com área zero.

    Somá-los poria no relatório voo que não pulverizou nada. Sumir com eles em silêncio
    também não serve: a planilha tem mais linhas do que o relatório vai ter, e quem
    confere precisa saber por quê.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(quando="2026-08-15 19:25:14-19:25:21", area="0.0", volume="0.0", duracao="00:07"),
            _voo(quando="2026-08-15 19:44:57-19:45:34", area="0.0", volume="0.0", duracao="00:37"),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert len(leitura.aplicacoes) == 1
    assert leitura.voos_sem_aplicacao == 2
    assert any("não pulverizaram área" in aviso for aviso in leitura.avisos)
    # Eles continuam inteiros na leitura: é deles que sai o horímetro da frota.
    assert [voo.duracao.total_seconds() for voo in leitura.voos_auxiliares] == [7.0, 37.0]


# ----------------------------------------------------------------- os parâmetros do voo


def test_largura_e_altura_entram_quando_os_voos_concordam() -> None:
    """São dois campos do talão: largura da faixa e altura do voo (seção 4.6)."""
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
                largura="14.12",
                altura="6.0",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="150",
                volume="60",
                duracao="07:41",
                talhao="Milho 1",
                plot="plot-a",
                largura="14.12",
                altura="6.0",
            ),
        ]
    )

    aplicacao = smartfarm.ler(arquivo).aplicacoes[0]

    assert aplicacao.largura_faixa_m == Decimal("14.12")
    assert aplicacao.altura_voo_m == Decimal("6.0")


def test_parametro_que_divergiu_entre_voos_nao_vira_media() -> None:
    """Ou a aplicação foi feita com aquela faixa, ou alguém mudou algo no meio.

    Média entraria no documento como um número que não aconteceu em voo nenhum.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
                largura="14.12",
                altura="6.0",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="150",
                volume="60",
                duracao="07:41",
                talhao="Milho 1",
                plot="plot-a",
                largura="11.14",
                altura="7.0",
            ),
        ]
    )

    aplicacao = smartfarm.ler(arquivo).aplicacoes[0]

    assert aplicacao.largura_faixa_m is None
    assert aplicacao.altura_voo_m is None


def test_aeronave_trocada_no_meio_da_aplicacao_vira_aviso() -> None:
    """A aeronave vai no relatório mensal (art. 11, II). Duas num registro é divergência."""
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
                aeronave="Valkyria",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="150",
                volume="60",
                duracao="07:41",
                talhao="Milho 1",
                plot="plot-a",
                aeronave="Nebraska",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert any("mais de uma aeronave" in aviso for aviso in leitura.avisos)


# ----------------------------------------------------------------- horário e arquivo ruim


def test_o_horario_vem_como_esta_no_arquivo_e_o_fuso_e_avisado() -> None:
    """O arquivo não diz o fuso, e converter por palpite desloca o relatório em horas.

    Erraria também a conferência do clima, que confronta a leitura com o horário da
    aplicação — ver a seção 3 do discovery, sobre deriva.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert leitura.aplicacoes[0].comecou_em.isoformat() == "2026-08-15T18:51:36"
    assert leitura.aplicacoes[0].comecou_em.tzinfo is None
    assert any("fuso" in aviso for aviso in leitura.avisos)


def test_voo_que_atravessa_a_meia_noite_nao_termina_antes_de_comecar() -> None:
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 23:58:00-00:04:00",
                area="150",
                volume="60",
                duracao="06:00",
                talhao="Milho 1",
                plot="plot-a",
            ),
        ]
    )

    aplicacao = smartfarm.ler(arquivo).aplicacoes[0]

    assert aplicacao.terminou_em.isoformat() == "2026-08-16T00:04:00"


def test_arquivo_que_nao_e_planilha_nem_csv_e_recusado_com_recado_de_gente() -> None:
    with pytest.raises(smartfarm.PlanilhaInvalidaError, match="planilha nem um CSV"):
        smartfarm.ler(b"isto aqui nao e um zip")


def test_planilha_de_outra_coisa_e_recusada() -> None:
    """Planilha do mês passado do Excel dele, por engano, não pode virar meia importação."""
    arquivo = _planilha([["Produto", "Quantidade"], ["Glifosato", "20"]])

    with pytest.raises(smartfarm.PlanilhaInvalidaError, match="colunas de voo"):
        smartfarm.ler(arquivo)


def test_planilha_com_cabecalho_e_sem_voo_e_recusada() -> None:
    with pytest.raises(smartfarm.PlanilhaInvalidaError, match="nenhum voo"):
        smartfarm.ler(_planilha([CABECALHO]))


def test_o_que_variou_entre_voos_aparece_como_intervalo() -> None:
    """A altura varia de voo para voo porque é a que o equipamento voou.

    Média poria no documento um número que não aconteceu em voo nenhum. O intervalo diz o
    que aconteceu, e quem preenche o talão decide o que declarar.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
                altura="5.8",
            ),
            _voo(
                quando="2026-08-15 19:03:16-19:10:57",
                area="150",
                volume="60",
                duracao="07:41",
                talhao="Milho 1",
                plot="plot-a",
                altura="6.3",
            ),
        ]
    )

    aplicacao = smartfarm.ler(arquivo).aplicacoes[0]

    assert aplicacao.altura_voo_m is None
    assert aplicacao.altura_voo_intervalo == (Decimal("5.8"), Decimal("6.3"))


# ----------------------------------------------------------------- o horímetro da frota


def test_voo_auxiliar_nao_some_e_vai_para_o_horimetro() -> None:
    """Translado e calibração desgastam motor, hélice e bateria igual.

    Descartá-los faria a revisão vencer sem o sistema saber. O relatório do MAPA leva só a
    aplicação; a manutenção leva tudo — e por isso são duas listas, não uma filtrada.
    """
    arquivo = _planilha(
        [
            CABECALHO,
            _voo(
                quando="2026-08-15 18:51:36-18:58:23",
                area="150",
                volume="60",
                duracao="06:47",
                talhao="Milho 1",
                plot="plot-a",
            ),
            _voo(quando="2026-08-15 19:25:14-19:33:35", area="0.0", volume="0.0", duracao="08:21"),
        ]
    )

    leitura = smartfarm.ler(arquivo)

    assert len(leitura.aplicacoes) == 1
    assert len(leitura.voos_auxiliares) == 1
    assert leitura.voos_auxiliares[0].duracao == timedelta(minutes=8, seconds=21)

    horimetro = leitura.horimetro[0]
    assert horimetro.voos == 2
    assert horimetro.duracao_total == timedelta(minutes=15, seconds=8)
    assert horimetro.duracao_aplicando == timedelta(minutes=6, seconds=47)
    assert horimetro.duracao_auxiliar == timedelta(minutes=8, seconds=21)


def test_o_horimetro_e_por_equipamento_e_nao_por_apelido() -> None:
    """Duas aeronaves no mesmo arquivo são dois horímetros.

    A conta é pelo número de série, porque é ele que identifica o equipamento: apelido o
    operador troca, e trocar o apelido não zera a hora de uso de nada.
    """
    primeira = _voo(
        quando="2026-08-15 18:51:36-18:58:23",
        area="150",
        volume="60",
        duracao="06:00",
        talhao="Milho 1",
        plot="plot-a",
    )
    segunda = _voo(
        quando="2026-07-19 10:02:05-10:05:59",
        area="0.0",
        volume="0.0",
        duracao="03:53",
        aeronave="Predador",
    )
    segunda[19] = "OUTRO-EQUIPAMENTO"

    leitura = smartfarm.ler(_planilha([CABECALHO, primeira, segunda]))

    assert len(leitura.horimetro) == 2
    por_serie = {h.equipamento_serie: h for h in leitura.horimetro}
    assert por_serie["B26WN5P0025A3T"].duracao_aplicando == timedelta(minutes=6)
    assert por_serie["OUTRO-EQUIPAMENTO"].duracao_aplicando == timedelta()
    assert por_serie["OUTRO-EQUIPAMENTO"].duracao_auxiliar == timedelta(minutes=3, seconds=53)


# ----------------------------------------------------------------- o mesmo dado em CSV


def _csv(linhas: list[list[str]], separador: str = ",") -> bytes:
    """Escrito como o aplicativo escreve: com aspas onde o texto tem o separador dentro.

    O endereço do voo tem vírgula ("Piracanjuba, Goias, Brazil"), e é isso que separa o
    CSV de verdade do ingênuo — que juntaria os campos e deslocaria todas as colunas.
    """
    saida = StringIO()
    csv.writer(saida, delimiter=separador, lineterminator="\n").writerows(linhas)
    return saida.getvalue().encode()


def test_o_mesmo_registro_em_csv_le_igual() -> None:
    """O aplicativo também exporta CSV, e o operador manda o que tiver na mão."""
    linhas = [
        CABECALHO,
        _voo(
            quando="2026-08-15 18:51:36-18:58:23",
            area="483",
            volume="290.34",
            duracao="06:47",
            talhao="Milho 1",
            plot="plot-a",
        ),
    ]

    leitura = smartfarm.ler(_csv(linhas))

    assert leitura.unidade_de_area == "mu"
    assert leitura.aplicacoes[0].area_ha == Decimal("32.2000")


def test_csv_com_ponto_e_virgula_tambem_le() -> None:
    """Planilha salva em computador com configuração brasileira sai assim.

    Ler uma com a regra da outra devolveria uma coluna só — e a tela diria "faltam as
    colunas de voo" para quem não errou nada.
    """
    linhas = [
        CABECALHO,
        _voo(
            quando="2026-08-15 18:51:36-18:58:23",
            area="483",
            volume="290.34",
            duracao="06:47",
            talhao="Milho 1",
            plot="plot-a",
        ),
    ]

    leitura = smartfarm.ler(_csv(linhas, separador=";"))

    assert leitura.aplicacoes[0].area_ha == Decimal("32.2000")
