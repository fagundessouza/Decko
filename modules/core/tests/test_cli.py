"""Normalização do identificador da empresa.

Os casos abaixo vieram de tentativas reais de uso: o formato exigido não é óbvio para quem
está cadastrando a própria empresa pela primeira vez.
"""

import pytest

from decko_modules.core.cli import normalize_slug


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("agrodrone", "agrodrone"),
        ("AgroDrone", "agrodrone"),
        ("Agro Drone", "agro-drone"),
        ("  AgroDrone  ", "agrodrone"),
        ("Agro_Drone", "agro-drone"),
        ("AgroDrone  Jataí", "agrodrone-jatai"),
        ("Distribuidora São João", "distribuidora-sao-joao"),
        ("Agro--Drone", "agro-drone"),
        ("-agrodrone-", "agrodrone"),
        ("Mercado 24h", "mercado-24h"),
    ],
)
def test_normalizes_common_input(digitado: str, esperado: str) -> None:
    assert normalize_slug(digitado) == esperado


@pytest.mark.parametrize("digitado", ["", "   ", "!!!", "---"])
def test_returns_empty_when_nothing_usable_remains(digitado: str) -> None:
    """String vazia sinaliza entrada inaproveitável, e o comando recusa com explicação."""
    assert normalize_slug(digitado) == ""
