import uuid
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator

from decko.documents import pydantic_cpf_cnpj
from decko_modules.clientes.models import TipoPessoa


def _optional_documento(value: str | None) -> str | None:
    """Campo em branco é ausência de documento; qualquer outra coisa é conferida.

    Cliente de balcão sem CPF é comum: exigir documento para vender um pão travaria a
    loja. O que não pode é aceitar um número que não fecha.
    """
    if value is None or value.strip() == "":
        return None
    return pydantic_cpf_cnpj(value)


def _so_digitos(value: str | None) -> str | None:
    if value is None:
        return None
    apenas = "".join(caractere for caractere in value if caractere.isdigit())
    return apenas or None


OptionalDocumento = Annotated[str | None, BeforeValidator(_optional_documento)]
OptionalCep = Annotated[str | None, BeforeValidator(_so_digitos)]


class ClienteIn(BaseModel):
    tipo: TipoPessoa = TipoPessoa.FISICA
    nome: str = Field(min_length=1, max_length=200)
    apelido: str | None = Field(default=None, max_length=200)

    cpf_cnpj: OptionalDocumento = None
    inscricao_estadual: str | None = Field(default=None, max_length=40)

    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=20)

    cep: OptionalCep = None
    logradouro: str | None = Field(default=None, max_length=200)
    numero: str | None = Field(default=None, max_length=20)
    complemento: str | None = Field(default=None, max_length=100)
    bairro: str | None = Field(default=None, max_length=100)
    cidade: str | None = Field(default=None, max_length=100)
    uf: str | None = Field(default=None, min_length=2, max_length=2)

    observacao: str | None = None

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, value: str | None) -> str | None:
        """``go`` e ``GO`` são a mesma unidade federativa; guardar as duas não é."""
        return value.upper() if value else value


class ClienteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: TipoPessoa
    nome: str
    apelido: str | None

    cpf_cnpj: str | None
    inscricao_estadual: str | None

    email: str | None
    telefone: str | None

    cep: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    cidade: str | None
    uf: str | None

    observacao: str | None
    ativo: bool
