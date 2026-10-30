"""Obtenção e avaliação das condições meteorológicas de uma aplicação.

O relatório é preenchido depois do voo, às vezes dias depois. Por isso o que importa aqui
não é "o tempo agora", e sim o tempo naquela coordenada naquele horário — e, junto dele,
de onde o dado veio. Uma leitura sem origem registrada não serve como prova em disputa de
deriva, que é o risco que este módulo existe para endereçar.

Ver docs/discovery/agro-planejamento-operacional.md, seção 3.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

# A partir deste ponto no passado, o conjunto reanalisado já está consolidado e é a fonte
# mais defensável. Antes disso ele ainda não publicou, e só o modelo de previsão tem o
# período recente.
ARCHIVE_THRESHOLD_DAYS = 6

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_FIELDS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"


class WeatherUnavailableError(RuntimeError):
    """O provedor não respondeu ou não tem dado para aquele instante e coordenada."""


@dataclass(frozen=True)
class Observation:
    """Uma leitura, com a procedência junto. Os dois andam sempre juntos."""

    temperatura_c: Decimal | None
    umidade_relativa_pct: Decimal | None
    velocidade_vento_kmh: Decimal | None
    # Graus, de onde o vento vem. A norma de drone exige direção, não só velocidade.
    direcao_vento_graus: Decimal | None
    observed_at: datetime
    provider: str
    payload: dict[str, Any]


class WeatherProvider(Protocol):
    async def observe(
        self, *, latitude: Decimal, longitude: Decimal, moment: datetime
    ) -> Observation: ...


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class OpenMeteoProvider:
    """Open-Meteo: sem chave de API e com histórico por coordenada.

    A escolha do endpoint fica registrada em ``provider``, de modo que o documento diz de
    qual conjunto de dados a leitura saiu em vez de deixar isso implícito.
    """

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 15.0) -> None:
        self._client = client
        self._timeout = timeout

    async def observe(
        self, *, latitude: Decimal, longitude: Decimal, moment: datetime
    ) -> Observation:
        use_archive = (datetime.now(UTC) - _as_utc(moment)) > timedelta(days=ARCHIVE_THRESHOLD_DAYS)
        url = ARCHIVE_URL if use_archive else FORECAST_URL
        dataset = "open-meteo/archive" if use_archive else "open-meteo/forecast"

        # Os dois endpoints aceitam janela de datas, então pedimos só o dia necessário.
        # Pedir a janela ampla trazia 2232 horas (80 KB) para extrair uma leitura; o dia
        # isolado traz 24 horas (1,3 KB), e o aparelho em campo costuma estar em rede ruim.
        day = moment.date().isoformat()
        params: dict[str, Any] = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "hourly": HOURLY_FIELDS,
            "wind_speed_unit": "kmh",
            "timezone": "auto",
            "start_date": day,
            "end_date": day,
        }

        payload = await self._get(url, params)
        return _extract(payload, moment, dataset)

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.get(url, params=params, timeout=self._timeout)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # O tipo entra na mensagem porque exceções de tempo esgotado do httpx chegam
            # com texto vazio, e "indisponível: " sozinho não diz nada a quem for apurar.
            detail = str(exc) or type(exc).__name__
            raise WeatherUnavailableError(f"provedor de clima indisponível: {detail}") from exc

        body: dict[str, Any] = response.json()
        if "hourly" not in body:
            raise WeatherUnavailableError("resposta do provedor sem série horária")
        return body


def _as_utc(moment: datetime) -> datetime:
    """Trata horário sem fuso como UTC, para a comparação não depender do servidor."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _extract(payload: dict[str, Any], moment: datetime, dataset: str) -> Observation:
    """Escolhe a hora mais próxima do instante pedido.

    A série é horária e o formulário registra hora cheia, então a hora mais próxima é a
    granularidade correta — não uma aproximação conveniente.
    """
    hourly = payload["hourly"]
    times: list[str] = hourly.get("time") or []
    if not times:
        raise WeatherUnavailableError("série horária vazia")

    target = moment.replace(tzinfo=None)
    best_index = min(
        range(len(times)),
        key=lambda index: abs(datetime.fromisoformat(times[index]) - target),
    )
    observed = datetime.fromisoformat(times[best_index])

    # Uma série que não alcança o instante pedido devolveria a ponta dela como se fosse a
    # leitura correta. Preencher um documento legal com isso seria pior que falhar.
    if abs(observed - target) > timedelta(hours=1):
        raise WeatherUnavailableError(
            f"provedor não tem leitura para {target.isoformat()} nessa coordenada"
        )

    offset = timedelta(seconds=int(payload.get("utc_offset_seconds") or 0))

    return Observation(
        temperatura_c=_to_decimal(_at(hourly, "temperature_2m", best_index)),
        umidade_relativa_pct=_to_decimal(_at(hourly, "relative_humidity_2m", best_index)),
        velocidade_vento_kmh=_to_decimal(_at(hourly, "wind_speed_10m", best_index)),
        direcao_vento_graus=_to_decimal(_at(hourly, "wind_direction_10m", best_index)),
        observed_at=observed.replace(tzinfo=UTC) - offset,
        provider=dataset,
        payload={
            "request": {
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "timezone": payload.get("timezone"),
                "utc_offset_seconds": payload.get("utc_offset_seconds"),
                "elevation": payload.get("elevation"),
            },
            "units": payload.get("hourly_units"),
            "observation": {
                "time": times[best_index],
                "temperature_2m": _at(hourly, "temperature_2m", best_index),
                "relative_humidity_2m": _at(hourly, "relative_humidity_2m", best_index),
                "wind_speed_10m": _at(hourly, "wind_speed_10m", best_index),
                "wind_direction_10m": _at(hourly, "wind_direction_10m", best_index),
            },
            "retrieved_at": datetime.now(UTC).isoformat(),
        },
    )


def _at(hourly: dict[str, Any], field: str, index: int) -> object:
    values = hourly.get(field)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


@dataclass(frozen=True)
class ParameterLimits:
    """Limites planejados pelo responsável técnico para a aplicação."""

    temperatura_maxima_c: Decimal | None = None
    umidade_relativa_min_pct: Decimal | None = None
    velocidade_vento_max_kmh: Decimal | None = None


def _fmt(value: Decimal) -> str:
    """Sem zeros à direita: o operador lê "10 km/h", não "10.00 km/h"."""
    return f"{value.normalize():f}"


def evaluate(observation: Observation, limits: ParameterLimits) -> list[str]:
    """Devolve as violações encontradas, em texto legível pelo operador.

    Uma lista, e não um booleano, porque quem está no campo precisa saber **qual** limite
    foi rompido para decidir se adia a aplicação — essa é a parte que evita o processo,
    enquanto o registro apenas o documenta.
    """
    problems: list[str] = []

    wind = observation.velocidade_vento_kmh
    wind_limit = limits.velocidade_vento_max_kmh
    if wind is not None and wind_limit is not None and wind > wind_limit:
        problems.append(
            f"Vento de {_fmt(wind)} km/h acima do limite de "
            f"{_fmt(wind_limit)} km/h: risco de deriva."
        )

    temperature = observation.temperatura_c
    temperature_limit = limits.temperatura_maxima_c
    if (
        temperature is not None
        and temperature_limit is not None
        and temperature > temperature_limit
    ):
        problems.append(
            f"Temperatura de {_fmt(temperature)} °C acima do limite de "
            f"{_fmt(temperature_limit)} °C."
        )

    humidity = observation.umidade_relativa_pct
    humidity_floor = limits.umidade_relativa_min_pct
    if humidity is not None and humidity_floor is not None and humidity < humidity_floor:
        problems.append(
            f"Umidade relativa de {_fmt(humidity)}% abaixo do mínimo de {_fmt(humidity_floor)}%."
        )

    return problems
