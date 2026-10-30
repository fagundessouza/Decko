"""Leitura do KML que o piloto exporta do aplicativo do drone.

O que precisa sair certo: o contorno da área, a direção das faixas de aplicação e uma
coordenada da área — que é o que a IN 2/2008 pede do croqui, nos incisos XI e XIII do
art. 9º. O KML é padrão OGC; o que varia é quanto cada exportador coloca dentro dele.
"""

from decimal import Decimal

import pytest

from decko_modules.agro.croqui import CroquiInvalidoError, ler

# Um quadrado de 1 km de lado, perto de Jataí/GO. A 1 km do equador o grau vale pouco
# mais de 111 km em latitude, então 0,009° ≈ 1 km — e a área sai perto de 100 ha.
QUADRADO = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Talhao Norte</name>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        -51.7200,-17.8800,0 -51.7200,-17.8890,0 -51.7106,-17.8890,0 -51.7106,-17.8800,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
  </Document>
</kml>
"""

# Faixas de norte para sul: a direção dos tiros é zero grau.
COM_FAIXAS = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark><LineString><coordinates>
      -51.7200,-17.8800 -51.7200,-17.8890
    </coordinates></LineString></Placemark>
    <Placemark><LineString><coordinates>
      -51.7190,-17.8890 -51.7190,-17.8800
    </coordinates></LineString></Placemark>
    <Placemark><LineString><coordinates>
      -51.7180,-17.8800 -51.7180,-17.88005
    </coordinates></LineString></Placemark>
  </Document>
</kml>
"""

SEM_GEOMETRIA = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Vazio</name></Document></kml>
"""


def test_le_o_contorno_da_area() -> None:
    croqui = ler(QUADRADO)

    assert len(croqui.limite) == 4
    # Ordem (longitude, latitude), como no KML: trocar as duas é o erro clássico.
    lon, lat = croqui.limite[0]
    assert lon == pytest.approx(-51.72)
    assert lat == pytest.approx(-17.88)


def test_area_do_poligono_sai_em_hectares() -> None:
    """É sugestão, não o número do documento — mas precisa estar certa."""
    area = ler(QUADRADO).area_ha()

    assert area is not None
    # Um quadrado de aproximadamente um quilômetro de lado dá perto de 100 ha.
    assert Decimal("90") < area < Decimal("110")


def test_a_coordenada_da_area_sai_do_centro() -> None:
    centro = ler(QUADRADO).centro()

    assert centro is not None
    lon, lat = centro
    assert lon == pytest.approx(-51.7153, abs=0.001)
    assert lat == pytest.approx(-17.8845, abs=0.001)


def test_direcao_dos_tiros_sai_da_faixa_mais_longa() -> None:
    """Faixa curta é manobra, e puxaria a média para qualquer lado."""
    direcao = ler(COM_FAIXAS).direcao_dos_tiros()

    assert direcao is not None
    assert direcao == pytest.approx(Decimal(0), abs=Decimal("1"))


def test_ida_e_volta_dao_a_mesma_direcao() -> None:
    """Faixa é orientação, não sentido: o piloto alterna as duas no mesmo voo."""
    norte_sul = """<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><LineString>
      <coordinates>-51.72,-17.88 -51.72,-17.889</coordinates>
    </LineString></Placemark></kml>"""
    sul_norte = """<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><LineString>
      <coordinates>-51.72,-17.889 -51.72,-17.88</coordinates>
    </LineString></Placemark></kml>"""

    assert ler(norte_sul).direcao_dos_tiros() == ler(sul_norte).direcao_dos_tiros()


def test_faixa_leste_oeste_da_noventa_graus() -> None:
    leste_oeste = """<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><LineString>
      <coordinates>-51.72,-17.88 -51.711,-17.88</coordinates>
    </LineString></Placemark></kml>"""

    direcao = ler(leste_oeste).direcao_dos_tiros()
    assert direcao == pytest.approx(Decimal(90), abs=Decimal("1"))


def test_altitude_e_descartada_sem_quebrar() -> None:
    """O croqui é desenho em planta; o terceiro número do KML não entra."""
    croqui = ler(QUADRADO)

    assert all(len(ponto) == 2 for ponto in croqui.limite)


def test_xml_que_nao_e_kml_manda_procurar_no_lugar_certo() -> None:
    """Mandar a nota fiscal por engano não pode responder "não encontrei área"."""
    with pytest.raises(CroquiInvalidoError, match="não é um KML"):
        ler("<html><body>isto não é um KML</body></html>")


def test_arquivo_que_nao_e_xml_e_recusado() -> None:
    with pytest.raises(CroquiInvalidoError, match="KML válido"):
        ler("isto não é nem XML")


def test_kmz_e_aceito_porque_e_o_que_o_aplicativo_entrega() -> None:
    """Recusar o arquivo que o piloto tem na mão, pela embalagem, seria defeito."""
    import io as _io
    import zipfile as _zipfile

    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr("doc.kml", QUADRADO)

    croqui = ler(buffer.getvalue())

    assert len(croqui.limite) == 4


def test_kml_sem_geometria_e_recusado() -> None:
    with pytest.raises(CroquiInvalidoError, match="rota"):
        ler(SEM_GEOMETRIA)


def test_coordenada_fora_do_mundo_e_ignorada() -> None:
    """Erro de exportação não vira ponto no desenho."""
    torto = """<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><LineString>
      <coordinates>-51.72,-17.88 999,999 -51.711,-17.88</coordinates>
    </LineString></Placemark></kml>"""

    assert len(ler(torto).faixas[0]) == 2


def test_area_exige_poligono() -> None:
    """Rota de voo sozinha não fecha área, e inventar um fechamento daria outro número."""
    assert ler(COM_FAIXAS).area_ha() is None
