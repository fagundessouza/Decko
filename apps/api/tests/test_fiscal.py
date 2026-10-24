"""NCM e CEST: o que é aceito, o que é recusado e o que volta formatado.

Requisito e limites em ``docs/discovery/comercial-produto-fiscal.md``.
"""

import pytest
from pydantic_core import PydanticCustomError

from decko.fiscal import (
    InvalidFiscalCodeError,
    format_cest,
    format_ncm,
    pydantic_optional_cest,
    pydantic_optional_ncm,
    validate_cest,
    validate_ncm,
)


@pytest.mark.parametrize(
    "digitado",
    ["21069090", "2106.90.90", "2106 90 90", "2106-90-90"],
)
def test_ncm_aceita_como_a_pessoa_digita(digitado: str) -> None:
    """A máscara vem do edital, da nota ou da cabeça de quem digita. Todas valem."""
    assert validate_ncm(digitado) == "21069090"


def test_cest_aceita_com_e_sem_mascara() -> None:
    assert validate_cest("17.004.00") == "1700400"
    assert validate_cest("1700400") == "1700400"


@pytest.mark.parametrize("curto", ["2106909", "", "   ", "21"])
def test_ncm_curto_e_recusado(curto: str) -> None:
    with pytest.raises(InvalidFiscalCodeError, match="8 dígitos"):
        validate_ncm(curto)


def test_ncm_longo_e_recusado() -> None:
    with pytest.raises(InvalidFiscalCodeError):
        validate_ncm("210690901")


def test_campo_em_branco_e_ausencia_de_codigo() -> None:
    """Apagar o NCM errado precisa continuar possível."""
    assert pydantic_optional_ncm(None) is None
    assert pydantic_optional_ncm("") is None
    assert pydantic_optional_ncm("   ") is None


def test_erro_chega_ao_campo_sem_o_prefixo_do_pydantic() -> None:
    """``ValueError`` viraria "Value error, ..." na tela de quem está cadastrando."""
    with pytest.raises(PydanticCustomError) as erro:
        pydantic_optional_cest("123")
    assert str(erro.value).startswith("O CEST")


def test_mascara_volta_para_leitura() -> None:
    """O comprador confere esse número contra o edital, dígito a dígito."""
    assert format_ncm("21069090") == "2106.90.90"
    assert format_cest("1700400") == "17.004.00"


def test_codigo_fora_do_padrao_sai_como_esta() -> None:
    """Inventar uma máscara para o que não tem o tamanho certo esconderia o problema."""
    assert format_ncm("210") == "210"
    assert format_ncm(None) is None


def test_ncm_bem_formado_mas_inexistente_passa() -> None:
    """A conferência é de formato, não de existência — está dito no discovery.

    Este teste existe para o limite ser uma decisão registrada, e não uma surpresa no dia
    em que alguém descobrir que 99999999 entrou no cadastro.
    """
    assert validate_ncm("99999999") == "99999999"
