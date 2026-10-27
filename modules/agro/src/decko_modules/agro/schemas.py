import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from decko.documents import pydantic_cpf_cnpj
from decko_modules.agro.enums import Cultura, Momento, Periodo, PlanStatus, TipoAplicacao


class ClientIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    # Guardado sem máscara e conferido pelo dígito verificador: ver decko.documents.
    # O documento identifica o contratante num registro com efeito legal, então entrar
    # errado aqui sai errado no papel que vai para a fiscalização.
    cpf_cnpj: Annotated[str, BeforeValidator(pydantic_cpf_cnpj)]
    telefone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    cpf_cnpj: str
    telefone: str | None
    email: str | None


class AircraftIn(BaseModel):
    prefixo: str = Field(min_length=1, max_length=20)
    modelo: str | None = Field(default=None, max_length=120)
    fabricante: str | None = Field(default=None, max_length=120)


class AircraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prefixo: str
    modelo: str | None
    fabricante: str | None
    is_active: bool


class PilotIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    # Código ANAC do aeronavegante, impresso ao lado da assinatura do piloto.
    canac: str | None = Field(default=None, max_length=20)
    # Preenchido quando o piloto também assina como engenheiro agrônomo — na AgroDrone é
    # a mesma pessoa.
    crea: str | None = Field(default=None, max_length=40)
    cpf: str | None = Field(default=None, max_length=14)
    telefone: str | None = Field(default=None, max_length=20)


class PilotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    canac: str | None
    crea: str | None
    cpf: str | None
    telefone: str | None
    is_active: bool


class PropertyIn(BaseModel):
    client_id: uuid.UUID
    nome: str = Field(min_length=1, max_length=200)
    municipio: str = Field(min_length=1, max_length=120)
    uf: str = Field(min_length=2, max_length=2)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    nome: str
    municipio: str
    uf: str
    latitude: Decimal | None
    longitude: Decimal | None


class PlanIn(BaseModel):
    client_id: uuid.UUID
    property_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    # Quem voou. Antes o nome do piloto só existia dentro da assinatura.
    pilot_id: uuid.UUID | None = None
    # O formulário remete as precauções de uso ao receituário. Fica opcional aqui porque
    # o planejamento nasce rascunho, antes de o receituário estar em mãos.
    prescription_id: uuid.UUID | None = None
    data_aplicacao: date | None = None
    cultura: Cultura | None = None
    cultura_outras_texto: str | None = Field(default=None, max_length=120)
    tipos_aplicacao: list[TipoAplicacao] | None = None
    area_ha: Decimal | None = Field(default=None, ge=0)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    # Limites da aplicação. São o que transforma uma leitura meteorológica em alerta.
    param_temperatura_maxima_c: Decimal | None = None
    param_umidade_relativa_min_pct: Decimal | None = Field(default=None, ge=0, le=100)
    param_velocidade_vento_max_kmh: Decimal | None = Field(default=None, ge=0)
    param_largura_faixa_m: Decimal | None = Field(default=None, ge=0)
    param_altura_voo_m: Decimal | None = Field(default=None, ge=0)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int
    status: PlanStatus
    client_id: uuid.UUID
    property_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    pilot_id: uuid.UUID | None
    prescription_id: uuid.UUID | None
    data_aplicacao: date | None
    cultura: Cultura | None
    area_ha: Decimal | None
    param_temperatura_maxima_c: Decimal | None
    param_umidade_relativa_min_pct: Decimal | None
    param_velocidade_vento_max_kmh: Decimal | None


class WeatherCaptureIn(BaseModel):
    data: date
    periodo: Periodo
    momento: Momento
    # Obrigatório: só quem voou sabe a hora exata, e inferi-la falsearia o documento.
    hora: time
    # Informadas pelo aparelho em campo; na ausência, caem para o planejamento ou a
    # propriedade.
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class WeatherReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data: date
    periodo: Periodo
    momento: Momento
    hora: time | None
    temperatura_c: Decimal | None
    umidade_relativa_pct: Decimal | None
    velocidade_vento_kmh: Decimal | None
    source: str
    provider: str | None
    captured_at: datetime | None
    violou_parametro: bool


class WeatherCaptureOut(BaseModel):
    leitura: WeatherReadingOut
    # Vazio significa aplicação dentro dos limites planejados.
    alertas: list[str]


class ProductIn(BaseModel):
    nome_comercial: str = Field(min_length=1, max_length=200)
    formulacao: str | None = Field(default=None, max_length=120)
    classe_toxicologica: str | None = Field(default=None, max_length=40)
    registro_mapa: str | None = Field(default=None, max_length=60)
    is_adjuvante: bool = False


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome_comercial: str
    formulacao: str | None
    classe_toxicologica: str | None
    registro_mapa: str | None
    is_adjuvante: bool


class PrescriptionIn(BaseModel):
    numero: str = Field(min_length=1, max_length=60)
    emitido_em: date
    agronomo_nome: str | None = Field(default=None, max_length=200)
    agronomo_crea: str | None = Field(default=None, max_length=40)


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    emitido_em: date
    agronomo_nome: str | None
    agronomo_crea: str | None


class PlanProductIn(BaseModel):
    product_id: uuid.UUID
    dosagem_ha: Decimal | None = Field(default=None, ge=0)
    volume_ha: Decimal | None = Field(default=None, ge=0)
    # Não é derivado de dosagem por área: o talão traz a coluna e o receituário dita o
    # valor. Qual área multiplicar (planejada ou aplicada) é a questão Q9 do discovery.
    total_produto: Decimal | None = Field(default=None, ge=0)
    adjuvante: str | None = Field(default=None, max_length=200)


class PlanProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    # Cópia feita na inclusão da linha, não o valor atual do cadastro.
    formulacao: str | None
    classe_toxicologica: str | None
    dosagem_ha: Decimal | None
    volume_ha: Decimal | None
    total_produto: Decimal | None
    adjuvante: str | None


class PlanPrescriptionIn(BaseModel):
    """Vínculo do receituário feito depois, quando o documento chega às mãos de quem voa."""

    prescription_id: uuid.UUID | None


class ConsolidationPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int
    status: str
    data_aplicacao: date | None
    contratante: str
    contratante_documento: str
    propriedade: str
    municipio: str
    uf: str
    cultura: str
    area_ha: Decimal | None
    aeronave: str
    produtos: list[str]
    leituras: int
    violacoes: int


class ProductTotalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    produto: str
    total: Decimal


class ConsolidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ano: int
    mes: int
    quantidade: int
    area_total_ha: Decimal
    # O número que a empresa precisa ver antes de enviar o mês, não depois da autuação.
    planos_com_violacao: int
    # Planejamento sem data não cabe em mês nenhum; contado para não sumir da conferência.
    planos_sem_data: int
    totais_por_produto: list[ProductTotalOut]
    planos: list[ConsolidationPlanOut]


class MonthlyReportRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    municipio: str
    uf: str
    aeronave: str
    tipo_atividade: str
    area_ha: Decimal
    horas: Decimal
    # "marca comercial, volume e dosagem aplicada", do inciso V, já montado para leitura.
    produtos: list[str]


class MonthlyReportOut(BaseModel):
    """O relatório mensal do operador de ARP — Portaria MAPA 298/2021, art. 11."""

    ano: int
    mes: int
    linhas: list[MonthlyReportRowOut]
    area_total_ha: Decimal
    horas_totais: Decimal
    # Rascunho não é atividade realizada e fica de fora. Contado para não sumir calado.
    rascunhos_no_mes: int
    # Dia 15 do mês seguinte, que é quando a entrega vence.
    prazo: date
