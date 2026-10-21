"""Conferência de CPF e CNPJ pelo dígito verificador.

Vive aqui, e não dentro de um módulo de negócio, porque mais de um já guarda o documento:
o `tenant` do core e o contratante do agro. A regra é da Receita Federal, não do domínio
de quem chama.

**CPF** — 11 dígitos, módulo 11 com pesos decrescentes.

**CNPJ** — 14 posições. Desde julho de 2026 as doze primeiras aceitam letras maiúsculas
além de números; os dois dígitos verificadores continuam numéricos. O cálculo segue o
módulo 11, com cada caractere convertido pelo valor ASCII menos 48, de modo que os
algarismos mantêm o próprio valor e ``A`` vale 17. A fonte é a pergunta 14 de "CNPJ
alfanumérico — Perguntas e Respostas", da Receita Federal, cujo exemplo trabalhado
(``12.ABC.345/01DE-35``) está fixado nos testes:

    https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/cnpj/cnpj-alfanumerico.pdf

O documento oficial mostra apenas o caso ``dígito = 11 - resto``. Quando o resto é 0 ou 1
o dígito é 0, porque 11 e 10 não cabem em uma posição — é o mesmo tratamento do módulo 11
do CNPJ numérico, em uso há décadas, e não uma escolha nossa.

Documento com todos os caracteres iguais é recusado. Os onze CPFs desse tipo passam na
conta, e ``00000000000000`` também: são campo preenchido para escapar da validação, não
documento.
"""

from pydantic_core import PydanticCustomError

CPF_LENGTH = 11
CNPJ_LENGTH = 14

# Pesos do módulo 11. O segundo dígito repete a conta já com o primeiro anexado, por isso
# tem um peso a mais na frente.
CPF_FIRST_WEIGHTS = (10, 9, 8, 7, 6, 5, 4, 3, 2)
CPF_SECOND_WEIGHTS = (11, 10, 9, 8, 7, 6, 5, 4, 3, 2)
CNPJ_FIRST_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
CNPJ_SECOND_WEIGHTS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

# Subtraído do código ASCII. É o que a Receita define para o CNPJ alfanumérico, e o que
# faz '0'..'9' valerem 0..9.
ASCII_OFFSET = 48


class InvalidDocumentError(ValueError):
    """Documento que não passa na conferência. A mensagem é para quem está cadastrando."""


def strip_mask(raw: str) -> str:
    """Remove a formatação, preservando as letras do CNPJ alfanumérico."""
    return "".join(character for character in raw.upper() if character.isalnum())


def _check_digit(values: list[int], weights: tuple[int, ...]) -> int:
    remainder = sum(value * weight for value, weight in zip(values, weights, strict=True)) % 11
    return 0 if remainder < 2 else 11 - remainder


def _digits_of(document: str) -> list[int]:
    return [ord(character) - ASCII_OFFSET for character in document]


def is_valid_cpf(document: str) -> bool:
    if len(document) != CPF_LENGTH or not document.isdigit():
        return False
    if len(set(document)) == 1:
        return False

    values = _digits_of(document)
    first = _check_digit(values[:9], CPF_FIRST_WEIGHTS)
    second = _check_digit([*values[:9], first], CPF_SECOND_WEIGHTS)
    return values[9] == first and values[10] == second


def is_valid_cnpj(document: str) -> bool:
    if len(document) != CNPJ_LENGTH:
        return False
    base, verifiers = document[:12], document[12:]
    # As doze primeiras posições aceitam letra; as duas últimas, não.
    if not all(character.isdigit() or "A" <= character <= "Z" for character in base):
        return False
    if not verifiers.isdigit():
        return False
    if len(set(document)) == 1:
        return False

    values = _digits_of(base)
    first = _check_digit(values, CNPJ_FIRST_WEIGHTS)
    second = _check_digit([*values, first], CNPJ_SECOND_WEIGHTS)
    return [int(digit) for digit in verifiers] == [first, second]


def validate_cpf_cnpj(raw: str) -> str:
    """Devolve o documento sem máscara, ou recusa dizendo o que está errado.

    A mensagem distingue tamanho de dígito verificador de propósito: "tem 13 caracteres"
    manda conferir a digitação, enquanto "dígito verificador não confere" manda conferir o
    número no papel. São correções diferentes.
    """
    document = strip_mask(raw)

    if len(document) not in (CPF_LENGTH, CNPJ_LENGTH):
        raise InvalidDocumentError(
            f"Documento com {len(document)} caracteres: o CPF tem {CPF_LENGTH} e o CNPJ "
            f"tem {CNPJ_LENGTH}."
        )

    if len(document) == CPF_LENGTH:
        if not document.isdigit():
            raise InvalidDocumentError("CPF só tem números.")
        if not is_valid_cpf(document):
            raise InvalidDocumentError("CPF inválido: o dígito verificador não confere.")
        return document

    if not is_valid_cnpj(document):
        raise InvalidDocumentError("CNPJ inválido: o dígito verificador não confere.")
    return document


def pydantic_cpf_cnpj(raw: str) -> str:
    """Mesma conferência, com o erro no formato que o Pydantic entrega à interface.

    ``PydanticCustomError`` em vez de ``ValueError`` porque o Pydantic prefixa a mensagem
    do segundo com "Value error, ", e quem está no campo leria isso na tela.
    """
    try:
        return validate_cpf_cnpj(raw)
    except InvalidDocumentError as exc:
        raise PydanticCustomError("cpf_cnpj", str(exc)) from exc


def format_cpf_cnpj(document: str) -> str:
    """Põe a máscara de volta para impressão.

    O armazenamento é sem máscara, mas o documento impresso é conferido a olho contra o
    papel do contratante, e ninguém lê catorze caracteres corridos. A formatação do CNPJ
    alfanumérico é a mesma do numérico: a Receita manteve a máscara e as 14 posições.
    """
    if len(document) == CPF_LENGTH:
        return f"{document[:3]}.{document[3:6]}.{document[6:9]}-{document[9:]}"
    if len(document) == CNPJ_LENGTH:
        return f"{document[:2]}.{document[2:5]}.{document[5:8]}/{document[8:12]}-{document[12:]}"
    # Documento fora do padrão sai como está: inventar uma máscara esconderia o problema.
    return document
