"""Leitura meteorológica e avaliação dos limites da aplicação.

A resposta usada aqui foi gravada de uma chamada real à Open-Meteo para a região de
Jataí/GO, onde a operação acontece — está em ``fixtures/``. Serve a rede através de um
transporte de teste, de modo que o caminho HTTP real é exercitado sem depender de
conectividade nem variar a cada execução.
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from decko_modules.agro.weather import (
    Observation,
    OpenMeteoProvider,
    ParameterLimits,
    WeatherUnavailableError,
    evaluate,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "open_meteo_archive_jatai.json").read_text(
        encoding="utf-8"
    )
)

LATITUDE = Decimal("-17.8814")
LONGITUDE = Decimal("-51.7214")

# Valores conferidos na fixture: 2026-10-09 às 12:00, quente e seco.
RECORDED_DAY = FIXTURE["hourly"]["time"][12][:10]
RECORDED_TEMPERATURE = Decimal(str(FIXTURE["hourly"]["temperature_2m"][12]))
RECORDED_HUMIDITY = Decimal(str(FIXTURE["hourly"]["relative_humidity_2m"][12]))
RECORDED_WIND = Decimal(str(FIXTURE["hourly"]["wind_speed_10m"][12]))


def _provider(payload: dict | None = None) -> OpenMeteoProvider:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload if payload is not None else FIXTURE)

    return OpenMeteoProvider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_observe_reads_the_requested_hour() -> None:
    moment = datetime.fromisoformat(f"{RECORDED_DAY}T12:00")
    observation = await _provider().observe(latitude=LATITUDE, longitude=LONGITUDE, moment=moment)

    assert observation.temperatura_c == RECORDED_TEMPERATURE
    assert observation.umidade_relativa_pct == RECORDED_HUMIDITY
    assert observation.velocidade_vento_kmh == RECORDED_WIND


async def test_observation_carries_its_provenance() -> None:
    """O valor sem a origem não sustenta uma defesa; os dois são gravados juntos."""
    moment = datetime.fromisoformat(f"{RECORDED_DAY}T12:00")
    observation = await _provider().observe(latitude=LATITUDE, longitude=LONGITUDE, moment=moment)

    assert observation.provider.startswith("open-meteo/")
    assert observation.payload["units"]["wind_speed_10m"] == "km/h"
    assert observation.payload["observation"]["time"].endswith("12:00")
    assert observation.payload["retrieved_at"]


async def test_refuses_when_the_series_does_not_cover_the_moment() -> None:
    """Devolver a ponta da série como se fosse a leitura falsearia o documento."""
    moment = datetime.fromisoformat(f"{RECORDED_DAY}T12:00").replace(year=2020)

    with pytest.raises(WeatherUnavailableError):
        await _provider().observe(latitude=LATITUDE, longitude=LONGITUDE, moment=moment)


async def test_refuses_when_the_provider_returns_no_series() -> None:
    with pytest.raises(WeatherUnavailableError):
        await _provider({"latitude": -17.0}).observe(
            latitude=LATITUDE, longitude=LONGITUDE, moment=datetime(2026, 10, 9, 12, 0)
        )


def _observation(
    *, temperatura: str | None = None, umidade: str | None = None, vento: str | None = None
) -> Observation:
    return Observation(
        temperatura_c=Decimal(temperatura) if temperatura else None,
        umidade_relativa_pct=Decimal(umidade) if umidade else None,
        velocidade_vento_kmh=Decimal(vento) if vento else None,
        observed_at=datetime(2026, 10, 9, 15, 0),
        provider="open-meteo/archive",
        payload={},
    )


def test_wind_above_the_limit_is_flagged_as_drift_risk() -> None:
    problems = evaluate(
        _observation(vento="18.4"),
        ParameterLimits(velocidade_vento_max_kmh=Decimal("10")),
    )

    assert len(problems) == 1
    assert "deriva" in problems[0]


def test_recorded_conditions_against_a_strict_plan() -> None:
    """As condições gravadas — 34,5 °C e 26% — violam um planejamento conservador."""
    problems = evaluate(
        _observation(
            temperatura=str(RECORDED_TEMPERATURE),
            umidade=str(RECORDED_HUMIDITY),
            vento=str(RECORDED_WIND),
        ),
        ParameterLimits(
            temperatura_maxima_c=Decimal("30"),
            umidade_relativa_min_pct=Decimal("50"),
            velocidade_vento_max_kmh=Decimal("15"),
        ),
    )

    assert len(problems) == 2  # temperatura e umidade; o vento estava dentro


def test_nothing_is_flagged_when_within_the_limits() -> None:
    problems = evaluate(
        _observation(temperatura="24", umidade="65", vento="8"),
        ParameterLimits(
            temperatura_maxima_c=Decimal("30"),
            umidade_relativa_min_pct=Decimal("50"),
            velocidade_vento_max_kmh=Decimal("15"),
        ),
    )

    assert problems == []


def test_a_limit_that_was_not_planned_is_not_enforced() -> None:
    """Sem limite definido pelo responsável técnico, não há o que violar."""
    problems = evaluate(_observation(vento="40"), ParameterLimits())

    assert problems == []
