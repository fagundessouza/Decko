"""O croqui da área, lido do KML que o piloto exporta.

O formulário exige *"croqui da área a ser tratada, indicando seus limites... e coordenadas
geográficas em pelo menos um ponto"* e *"direção das faixas de aplicação (tiros) e o
sentido do vento"* — IN 2/2008, art. 9º, incisos XI e XIII. Hoje isso é desenhado à mão no
talão, e é a dor nº 4 do discovery.

**Por que KML.** A DJI não publica API do SmartFarm nem do Agras Management Platform. O
que existe é a exportação da rota de voo em KML, feita pelo próprio piloto — ver
``docs/discovery/agro-normas-mapa.md``, seção 7. Então a entrada é um arquivo, não uma
integração, e isso é decisão, não limitação temporária.

**O que este módulo não faz.** Não altera a área do planejamento. A área declarada é do
agrônomo responsável, e o número calculado do polígono entra como **sugestão** ao lado
dela. Sobrescrever mudaria um campo de documento legal a partir de um desenho.
"""

import io
import math
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal

from defusedxml import ElementTree

# Raio médio da Terra. Entra no cálculo de área e de distância.
EARTH_RADIUS_M = 6_371_008.8
# Abaixo disto a linha é ruído de exportação, não faixa de aplicação.
MIN_LINE_LENGTH_M = 5.0


class CroquiInvalidoError(ValueError):
    """O arquivo não é um KML legível. A mensagem vai para a tela de quem enviou."""


@dataclass
class Croqui:
    """A geometria da área, como ela sai do arquivo.

    Coordenadas em graus decimais, na ordem (longitude, latitude) — que é a do KML, e
    mantê-la evita a troca silenciosa que é o erro clássico deste formato.
    """

    # Contorno da área tratada, quando o arquivo traz polígono.
    limite: list[tuple[float, float]] = field(default_factory=list)
    # As faixas de aplicação. Cada uma é uma sequência de pontos.
    faixas: list[list[tuple[float, float]]] = field(default_factory=list)
    origem: str | None = None

    @property
    def vazio(self) -> bool:
        return not self.limite and not self.faixas

    def pontos(self) -> list[tuple[float, float]]:
        return [ponto for faixa in self.faixas for ponto in faixa] + self.limite

    def centro(self) -> tuple[float, float] | None:
        """O ponto que representa a área — serve à coordenada que o formulário pede."""
        todos = self.pontos()
        if not todos:
            return None
        return (
            sum(lon for lon, _lat in todos) / len(todos),
            sum(lat for _lon, lat in todos) / len(todos),
        )

    def area_ha(self) -> Decimal | None:
        """Área do polígono, em hectares. **Sugestão**, não o valor do documento."""
        if len(self.limite) < 3:
            return None
        return Decimal(str(round(_area_m2(self.limite) / 10_000, 4)))

    def direcao_dos_tiros(self) -> Decimal | None:
        """O rumo das faixas de aplicação, em graus de 0 a 180.

        Zero a 180 porque faixa é orientação, não sentido: ir de norte para sul e de sul
        para norte é a mesma direção de tiro, e o piloto alterna as duas no mesmo voo.

        Sai da faixa mais longa, e não da média: numa exportação real há trechos curtos de
        manobra e deslocamento entre talhões, e eles puxariam a média para qualquer lado.
        """
        maior: tuple[float, list[tuple[float, float]]] | None = None
        for faixa in self.faixas:
            if len(faixa) < 2:
                continue
            comprimento = sum(_distancia_m(faixa[i], faixa[i + 1]) for i in range(len(faixa) - 1))
            if comprimento >= MIN_LINE_LENGTH_M and (maior is None or comprimento > maior[0]):
                maior = (comprimento, faixa)

        if maior is None:
            return None

        faixa = maior[1]
        rumo = _rumo(faixa[0], faixa[-1])
        return Decimal(str(round(rumo % 180, 2)))


def ler(xml: str | bytes, *, origem: str | None = None) -> Croqui:
    """Lê o KML ou o KMZ. Levanta ``CroquiInvalidoError`` com o motivo.

    Lido com ``defusedxml`` porque o arquivo vem de fora: o parser padrão aceita entidade
    externa, e um arquivo preparado lê arquivo do servidor ou trava o processo.
    """
    conteudo = _descompactar_se_kmz(xml)

    try:
        raiz = ElementTree.fromstring(conteudo)
    # Qualquer falha de leitura é arquivo inválido, e a mensagem precisa ser uma só.
    except Exception as exc:
        raise CroquiInvalidoError("O arquivo não é um KML válido.") from exc

    # XML válido não é KML. Sem esta conferência, mandar a nota fiscal por engano
    # responderia "não encontrei área", que manda a pessoa procurar o problema no drone.
    if _sem_namespace(raiz.tag) != "kml":
        raise CroquiInvalidoError(
            "O arquivo é um XML, mas não é um KML. Exporte a rota de voo pelo aplicativo do drone."
        )

    croqui = Croqui(origem=origem)
    for elemento in raiz.iter():
        marca = _sem_namespace(elemento.tag)
        if marca not in ("LineString", "LinearRing", "Polygon", "Point"):
            continue

        for filho in elemento.iter():
            if _sem_namespace(filho.tag) != "coordinates" or not filho.text:
                continue
            pontos = _coordenadas(filho.text)
            if not pontos:
                continue
            # LinearRing dentro de Polygon é o contorno; o resto é faixa de voo.
            if marca in ("Polygon", "LinearRing") and not croqui.limite:
                croqui.limite = pontos
            elif marca == "LineString":
                croqui.faixas.append(pontos)

    if croqui.vazio:
        raise CroquiInvalidoError(
            "Não encontrei área nem rota neste KML. Exporte a rota de voo pelo aplicativo do drone."
        )
    return croqui


def _descompactar_se_kmz(conteudo: str | bytes) -> str | bytes:
    """KMZ é um zip com o KML dentro, e é o que o aplicativo costuma entregar.

    Recusar o arquivo que o piloto tem na mão, por causa da embalagem, seria defeito
    disfarçado de validação.
    """
    if not isinstance(conteudo, bytes) or not conteudo.startswith(b"PK"):
        return conteudo

    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            nomes = [nome for nome in pacote.namelist() if nome.lower().endswith(".kml")]
            if not nomes:
                raise CroquiInvalidoError("O KMZ não tem nenhum arquivo .kml dentro.")
            return pacote.read(nomes[0])
    except zipfile.BadZipFile as exc:
        raise CroquiInvalidoError("O arquivo não é um KML válido.") from exc


def _sem_namespace(tag: str) -> str:
    """``{http://www.opengis.net/kml/2.2}Placemark`` vira ``Placemark``."""
    return tag.rsplit("}", 1)[-1]


def _coordenadas(texto: str) -> list[tuple[float, float]]:
    """Lê o bloco ``<coordinates>``: ``lon,lat[,alt]`` separados por espaço ou quebra.

    A altitude é descartada: o croqui é desenho em planta, e o que a norma pede é limite
    e direção.
    """
    pontos: list[tuple[float, float]] = []
    for pedaco in re.split(r"\s+", texto.strip()):
        if not pedaco:
            continue
        partes = pedaco.split(",")
        if len(partes) < 2:
            continue
        try:
            lon, lat = float(partes[0]), float(partes[1])
        except ValueError:
            continue
        # Coordenada fora do mundo é erro de arquivo, não ponto a desenhar.
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            pontos.append((lon, lat))
    return pontos


def _metros_por_grau(latitude: float) -> tuple[float, float]:
    """Quanto vale um grau, em metros, naquela latitude.

    Projeção equirretangular centrada no talhão. Para uma área de alguns quilômetros o
    erro é desprezível, e ela evita trazer uma biblioteca de geodésia para desenhar um
    croqui. Para área continental não serviria — e não é o caso aqui.
    """
    por_grau = math.pi * EARTH_RADIUS_M / 180
    return por_grau * math.cos(math.radians(latitude)), por_grau


def _distancia_m(origem: tuple[float, float], destino: tuple[float, float]) -> float:
    lon1, lat1 = origem
    lon2, lat2 = destino
    mx, my = _metros_por_grau((lat1 + lat2) / 2)
    return math.hypot((lon2 - lon1) * mx, (lat2 - lat1) * my)


def _rumo(origem: tuple[float, float], destino: tuple[float, float]) -> float:
    """Rumo em graus a partir do norte, no sentido horário."""
    lon1, lat1 = origem
    lon2, lat2 = destino
    mx, my = _metros_por_grau((lat1 + lat2) / 2)
    leste = (lon2 - lon1) * mx
    norte = (lat2 - lat1) * my
    return math.degrees(math.atan2(leste, norte)) % 360


def _area_m2(poligono: list[tuple[float, float]]) -> float:
    """Área por fórmula do laço, sobre o polígono projetado em metros."""
    latitude_media = sum(lat for _lon, lat in poligono) / len(poligono)
    mx, my = _metros_por_grau(latitude_media)
    projetado = [(lon * mx, lat * my) for lon, lat in poligono]

    soma = 0.0
    for i in range(len(projetado)):
        x1, y1 = projetado[i]
        x2, y2 = projetado[(i + 1) % len(projetado)]
        soma += x1 * y2 - x2 * y1
    return abs(soma) / 2
