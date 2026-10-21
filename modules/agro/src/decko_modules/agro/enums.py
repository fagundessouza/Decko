"""Conjuntos fechados do formulário de Planejamento Operacional.

Os valores vêm do talão em uso, não de suposição. Acrescentar um valor exige migração,
o que é o comportamento desejado: o documento tem efeito legal e a lista do formulário
não muda por conveniência de quem programa.
"""

from enum import StrEnum


class Cultura(StrEnum):
    PASTAGENS = "pastagens"
    CANA_DE_ACUCAR = "cana_de_acucar"
    CAFE = "cafe"
    MILHO = "milho"
    CITRUS = "citrus"
    EUCALIPTO = "eucalipto"
    SOJA = "soja"
    OUTRAS = "outras"


class TipoAplicacao(StrEnum):
    MATURADOR = "maturador"
    HERBICIDA = "herbicida"
    FUNGICIDA = "fungicida"
    INSETICIDA = "inseticida"
    ADUBACAO = "adubacao"
    OUTROS = "outros"


class EquipamentoTipo(StrEnum):
    BARRAS_BICOS = "barras_bicos"
    ELETROSTATICO = "eletrostatico"
    SOLIDOS = "solidos"
    ATOMIZADORES = "atomizadores"
    OUTROS = "outros"


class PlanStatus(StrEnum):
    RASCUNHO = "rascunho"
    CONCLUIDO = "concluido"
    ASSINADO = "assinado"
    ENVIADO = "enviado"


class Periodo(StrEnum):
    MATUTINO = "matutino"
    VESPERTINO = "vespertino"


class Momento(StrEnum):
    INICIO = "inicio"
    FINAL = "final"


class WeatherSource(StrEnum):
    """Origem de uma leitura meteorológica.

    Guardada porque é o que distingue um registro probatório de um palpite preenchido
    depois. Ver docs/discovery/agro-planejamento-operacional.md, seção 3.
    """

    API = "api"
    MANUAL = "manual"
    SENSOR = "sensor"


class SignatureRole(StrEnum):
    ENG_AGRONOMO = "eng_agronomo"
    PILOTO_AGRICOLA = "piloto_agricola"
    TEC_AGRICOLA_EXECUTOR = "tec_agricola_executor"
    PROPRIETARIO_PREPOSTO = "proprietario_preposto"


class MaintenanceMoment(StrEnum):
    INICIAL = "inicial"
    FINAL = "final"
