"""Conversão de coordenadas para o formato do formulário.

O sistema guarda grau decimal, que é o que o aparelho fornece e o que a API de clima
consome. O formulário do MAPA pede grau, minuto e segundo com a letra do hemisfério, e é
assim que precisa sair no documento impresso.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class DMS:
    graus: int
    minutos: int
    segundos: Decimal
    hemisferio: str

    def __str__(self) -> str:
        return f"{self.graus}° {self.minutos}' {self.segundos}\" {self.hemisferio}"


def _to_dms(value: Decimal, positivo: str, negativo: str) -> DMS:
    hemisferio = positivo if value >= 0 else negativo
    magnitude = abs(Decimal(value))

    graus = int(magnitude)
    resto_minutos = (magnitude - graus) * 60
    minutos = int(resto_minutos)
    segundos = ((resto_minutos - minutos) * 60).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 59,999" arredonda para 60,00" e precisa subir de casa, senão o documento sai com um
    # valor que não existe.
    if segundos >= 60:
        segundos -= 60
        minutos += 1
    if minutos >= 60:
        minutos -= 60
        graus += 1

    return DMS(graus=graus, minutos=minutos, segundos=segundos, hemisferio=hemisferio)


def latitude_to_dms(value: Decimal) -> DMS:
    return _to_dms(value, "N", "S")


def longitude_to_dms(value: Decimal) -> DMS:
    return _to_dms(value, "E", "W")


def format_coordinates(latitude: Decimal | None, longitude: Decimal | None) -> str:
    """Linha de coordenadas como o formulário a imprime."""
    if latitude is None or longitude is None:
        return ""
    return f"{latitude_to_dms(latitude)}    {longitude_to_dms(longitude)}"
