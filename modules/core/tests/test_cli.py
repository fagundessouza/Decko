"""Normalização do identificador da empresa.

Os casos abaixo vieram de tentativas reais de uso: o formato exigido não é óbvio para quem
está cadastrando a própria empresa pela primeira vez.
"""

import pytest

from decko_modules.core.cli import BootstrapError, normalize_slug, recusar_email_que_nao_entra


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


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("nathan@agrodrone.com.br", "nathan@agrodrone.com.br"),
        ("  Nathan@AgroDrone.com.br  ", "nathan@agrodrone.com.br"),
    ],
)
def test_aceita_email_que_o_login_aceita(digitado: str, esperado: str) -> None:
    assert recusar_email_que_nao_entra(digitado) == esperado


@pytest.mark.parametrize("digitado", ["alguem@empresa.local", "sem-arroba", "alguem@", "@dominio"])
def test_recusa_email_antes_de_criar_conta_que_nao_entra(digitado: str) -> None:
    """A régua é a do login, e ela corre **antes** de a empresa existir.

    O caso que motivou isto é o `.local`: o comando aceitava, criava a empresa e a conta,
    e a pessoa descobria na tela de entrada que o `EmailStr` recusa TLD reservado — sem
    caminho de volta pela interface.
    """
    with pytest.raises(BootstrapError):
        recusar_email_que_nao_entra(digitado)
