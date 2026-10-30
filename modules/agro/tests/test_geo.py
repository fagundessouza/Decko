"""Conversão de grau decimal para grau/minuto/segundo.

O sistema guarda decimal; o formulário do MAPA imprime DMS. Um erro aqui sai impresso no
documento legal sem que nada falhe.
"""

from decimal import Decimal

import pytest

from decko_modules.agro.geo import format_coordinates, latitude_to_dms, longitude_to_dms


def test_south_latitude_keeps_the_hemisphere() -> None:
    dms = latitude_to_dms(Decimal("-17.8814"))

    assert (dms.graus, dms.minutos, dms.hemisferio) == (17, 52, "S")
    assert dms.segundos == Decimal("53.04")


def test_west_longitude_keeps_the_hemisphere() -> None:
    dms = longitude_to_dms(Decimal("-51.7214"))

    assert (dms.graus, dms.minutos, dms.hemisferio) == (51, 43, "W")
    assert dms.segundos == Decimal("17.04")


def test_northern_and_eastern_hemispheres() -> None:
    assert latitude_to_dms(Decimal("10.5")).hemisferio == "N"
    assert longitude_to_dms(Decimal("10.5")).hemisferio == "E"


def test_zero_is_treated_as_positive_hemisphere() -> None:
    assert latitude_to_dms(Decimal("0")).hemisferio == "N"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("-17.0"), (17, 0, Decimal("0.00"))),
        (Decimal("-17.5"), (17, 30, Decimal("0.00"))),
        (Decimal("-17.25"), (17, 15, Decimal("0.00"))),
    ],
)
def test_round_values(valor: Decimal, esperado: tuple[int, int, Decimal]) -> None:
    dms = latitude_to_dms(valor)
    assert (dms.graus, dms.minutos, dms.segundos) == esperado


def test_rounding_up_carries_into_minutes() -> None:
    """59,999" arredonda para 60,00", que não existe: tem de virar o minuto seguinte."""
    dms = latitude_to_dms(Decimal("-17.0166666"))

    assert dms.segundos < 60
    assert (dms.graus, dms.minutos, dms.segundos) == (17, 1, Decimal("0.00"))


def test_formatted_line_has_both_coordinates() -> None:
    linha = format_coordinates(Decimal("-17.8814"), Decimal("-51.7214"))

    assert "17° 52' 53.04\" S" in linha
    assert "51° 43' 17.04\" W" in linha


def test_missing_coordinate_produces_empty_line() -> None:
    assert format_coordinates(None, Decimal("-51.7")) == ""
