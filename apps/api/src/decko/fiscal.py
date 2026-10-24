"""Códigos de classificação fiscal do produto.

Vive aqui, junto de ``documents.py``, e não dentro do módulo comercial: a regra é da
Receita Federal e do Confaz, não do domínio de quem guarda o campo. Quando o módulo fiscal
existir, ele vai precisar das mesmas funções.

**NCM** — Nomenclatura Comum do Mercosul, 8 dígitos, escrita ``0000.00.00``. Classifica a
mercadoria e é obrigatória na nota fiscal eletrônica. Quem compra por licitação pede o NCM
antes de pedir o preço, porque o edital exige a classificação do item ofertado — ver
``docs/discovery/comercial-produto-fiscal.md``.

**CEST** — Código Especificador da Substituição Tributária, 7 dígitos, escrito
``00.000.00``, do Convênio ICMS 142/2018. Só se aplica a mercadoria sujeita a substituição
tributária, e sempre acompanha um NCM.

**A conferência aqui é de formato, não de existência.** Oito dígitos passam, existindo ou
não na tabela da Receita. Validar contra a tabela oficial exigiria carregá-la e mantê-la
atualizada, o que é decisão em aberto no discovery — e um `None` silencioso seria pior que
um código conferido só no comprimento.
"""

from pydantic_core import PydanticCustomError

NCM_LENGTH = 8
CEST_LENGTH = 7


class InvalidFiscalCodeError(ValueError):
    pass


def strip_mask(raw: str) -> str:
    """Só os dígitos. O cadastro aceita ``2106.90.90`` e guarda ``21069090``."""
    return "".join(character for character in raw if character.isdigit())


def _validate(raw: str, *, length: int, name: str, example: str) -> str:
    code = strip_mask(raw)
    if len(code) != length:
        raise InvalidFiscalCodeError(f"{name} precisa ter {length} dígitos (exemplo: {example}).")
    return code


def validate_ncm(raw: str) -> str:
    return _validate(raw, length=NCM_LENGTH, name="O NCM", example="2106.90.90")


def validate_cest(raw: str) -> str:
    return _validate(raw, length=CEST_LENGTH, name="O CEST", example="17.004.00")


def _optional(validator):  # type: ignore[no-untyped-def]
    """Campo em branco é ausência de código; qualquer outra coisa é conferida.

    Apagar o campo precisa continuar possível — o produto pode ter sido cadastrado com o
    NCM errado, e corrigir às vezes começa por limpar.
    """

    def normalize(value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        try:
            return validator(value)
        except InvalidFiscalCodeError as exc:
            # PydanticCustomError em vez de ValueError: o Pydantic prefixa a mensagem do
            # segundo com "Value error, ", e quem está no campo leria isso na tela.
            raise PydanticCustomError("fiscal_code", str(exc)) from exc

    return normalize


pydantic_optional_ncm = _optional(validate_ncm)
pydantic_optional_cest = _optional(validate_cest)


def format_ncm(code: str | None) -> str | None:
    """Põe a máscara de volta para leitura: ``21069090`` vira ``2106.90.90``.

    O comprador confere esse número contra o edital, dígito a dígito. Oito caracteres
    corridos é o formato que faz errar.
    """
    if code is None or len(code) != NCM_LENGTH:
        return code
    return f"{code[:4]}.{code[4:6]}.{code[6:]}"


def format_cest(code: str | None) -> str | None:
    if code is None or len(code) != CEST_LENGTH:
        return code
    return f"{code[:2]}.{code[2:5]}.{code[5:]}"
