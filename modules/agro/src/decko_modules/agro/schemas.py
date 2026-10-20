import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.agro.enums import Cultura, Momento, Periodo, PlanStatus, TipoAplicacao


class ClientIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    # Só dígitos: a formatação é da interface, não do armazenamento.
    cpf_cnpj: str = Field(min_length=11, max_length=14, pattern=r"^\d+$")
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


class PlanIn(BaseModel):
    client_id: uuid.UUID
    property_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
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
