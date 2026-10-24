"""Conferência de CPF e CNPJ.

O caso que prende a regra é o exemplo trabalhado da própria Receita Federal, com as somas
intermediárias conferidas uma a uma: se alguém trocar um peso ou a conversão dos
caracteres, o número oficial deixa de fechar e o teste acusa onde.

Os CNPJs reais servem de contraprova. Foram escolhidos por serem públicos e verificáveis
fora daqui — se o algoritmo estivesse errado, dificilmente os três passariam.
"""

import pytest

from decko.documents import (
    CNPJ_FIRST_WEIGHTS,
    CNPJ_SECOND_WEIGHTS,
    InvalidDocumentError,
    format_cpf_cnpj,
    is_valid_cnpj,
    is_valid_cpf,
    strip_mask,
    validate_cpf_cnpj,
)
from decko.documents import _check_digit as check_digit
from decko.documents import _digits_of as digits_of

# "CNPJ alfanumérico — Perguntas e Respostas", pergunta 14, Receita Federal.
OFFICIAL_BASE = "12ABC34501DE"
OFFICIAL_CNPJ = "12ABC34501DE35"


def test_official_example_reproduces_every_intermediate_value() -> None:
    values = digits_of(OFFICIAL_BASE)
    assert values == [1, 2, 17, 18, 19, 3, 4, 5, 0, 1, 20, 21]

    first_sum = sum(v * w for v, w in zip(values, CNPJ_FIRST_WEIGHTS, strict=True))
    assert first_sum == 459
    first = check_digit(values, CNPJ_FIRST_WEIGHTS)
    assert first == 3

    second_sum = sum(v * w for v, w in zip([*values, first], CNPJ_SECOND_WEIGHTS, strict=True))
    assert second_sum == 424
    assert check_digit([*values, first], CNPJ_SECOND_WEIGHTS) == 5


def test_official_alphanumeric_cnpj_is_valid() -> None:
    assert is_valid_cnpj(OFFICIAL_CNPJ)


def test_a_wrong_check_digit_on_the_official_number_is_refused() -> None:
    assert not is_valid_cnpj("12ABC34501DE34")


@pytest.mark.parametrize(
    "cnpj",
    [
        "00000000000191",  # Banco do Brasil
        "33000167000101",  # Petrobras
        "60746948000112",  # Bradesco
    ],
)
def test_real_numeric_cnpj_still_validates(cnpj: str) -> None:
    """O formato numérico continua valendo: nenhuma empresa precisou trocar de número."""
    assert is_valid_cnpj(cnpj)


@pytest.mark.parametrize("cpf", ["11144477735", "12345678909"])
def test_valid_cpf_is_accepted(cpf: str) -> None:
    assert is_valid_cpf(cpf)


def test_cpf_with_a_transposed_digit_is_refused() -> None:
    """O erro que o dígito verificador existe para pegar: dois algarismos trocados."""
    assert is_valid_cpf("11144477735")
    assert not is_valid_cpf("11144477753")


@pytest.mark.parametrize("repeated", ["00000000000", "11111111111", "00000000000000"])
def test_a_document_of_repeated_characters_is_refused(repeated: str) -> None:
    """Passam na conta do módulo 11, mas são campo preenchido para escapar dela."""
    assert not is_valid_cpf(repeated)
    assert not is_valid_cnpj(repeated)


def test_letters_are_refused_in_the_check_digits() -> None:
    """As duas últimas posições continuam numéricas mesmo no CNPJ alfanumérico."""
    assert not is_valid_cnpj("12ABC34501DEDE")


def test_lowercase_letters_are_accepted_and_stored_uppercase() -> None:
    """Quem digita no celular não controla a caixa; o cadastro não pode depender disso."""
    assert validate_cpf_cnpj("12abc34501de35") == OFFICIAL_CNPJ


def test_the_mask_is_removed_and_the_letters_survive_it() -> None:
    assert strip_mask("12.ABC.345/01DE-35") == OFFICIAL_CNPJ
    assert validate_cpf_cnpj("12.ABC.345/01DE-35") == OFFICIAL_CNPJ
    assert validate_cpf_cnpj("111.444.777-35") == "11144477735"


def test_the_length_complaint_says_what_was_counted() -> None:
    """Tamanho errado manda conferir a digitação; dígito errado manda conferir o papel."""
    with pytest.raises(InvalidDocumentError, match="13 caracteres"):
        validate_cpf_cnpj("1234567800019")


def test_the_check_digit_complaint_names_the_document() -> None:
    with pytest.raises(InvalidDocumentError, match="CNPJ inválido"):
        validate_cpf_cnpj("12345678000199")

    with pytest.raises(InvalidDocumentError, match="CPF inválido"):
        validate_cpf_cnpj("11144477736")


def test_a_cpf_with_letters_is_refused() -> None:
    """Só o CNPJ ganhou letras. Onze posições com letra é erro de digitação."""
    with pytest.raises(InvalidDocumentError, match="CPF só tem números"):
        validate_cpf_cnpj("1114447773A")


def test_the_mask_comes_back_for_printing() -> None:
    """Guardado sem máscara, impresso com ela: o papel é conferido a olho."""
    assert format_cpf_cnpj("12345678000195") == "12.345.678/0001-95"
    assert format_cpf_cnpj("11144477735") == "111.444.777-35"
    # A Receita manteve a máscara e as 14 posições no formato alfanumérico.
    assert format_cpf_cnpj(OFFICIAL_CNPJ) == "12.ABC.345/01DE-35"


def test_a_document_of_unexpected_length_is_printed_as_it_is() -> None:
    """Inventar máscara para o que não encaixa esconderia o dado errado."""
    assert format_cpf_cnpj("123") == "123"
