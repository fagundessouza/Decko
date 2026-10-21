import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from decko.documents import pydantic_cpf_cnpj


def _optional_cnpj(value: str | None) -> str | None:
    """Campo em branco é ausência de CNPJ; qualquer outra coisa é conferida.

    Apagar o campo precisa continuar possível — a empresa pode tê-lo digitado errado e
    querer tirá-lo enquanto confere o papel.
    """
    if value is None or value.strip() == "":
        return None
    return pydantic_cpf_cnpj(value)


OptionalCnpj = Annotated[str | None, BeforeValidator(_optional_cnpj)]


class LoginRequest(BaseModel):
    # O e-mail é único por empresa, não globalmente, então o login precisa dizer em qual
    # empresa está entrando.
    tenant_slug: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    # Nome do esquema HTTP exigido pela RFC 6750, não um segredo.
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str


class TenantProfileOut(TenantOut):
    """A empresa como ela sai impressa no cabeçalho de um documento."""

    cnpj: str | None
    registro_mapa: str | None
    crea: str | None
    cda: str | None
    inscricao_estadual: str | None
    inscricao_municipal: str | None
    rodape: str | None


class TenantProfileIn(BaseModel):
    """Edição da identificação da empresa.

    O ``slug`` fica de fora: é o que a pessoa digita para entrar, e trocá-lo trancaria
    todo mundo do lado de fora. Entra num fluxo próprio, se um dia for preciso.
    """

    name: str = Field(min_length=1, max_length=200)
    cnpj: OptionalCnpj = None
    registro_mapa: str | None = Field(default=None, max_length=60)
    crea: str | None = Field(default=None, max_length=40)
    cda: str | None = Field(default=None, max_length=40)
    inscricao_estadual: str | None = Field(default=None, max_length=40)
    inscricao_municipal: str | None = Field(default=None, max_length=40)
    rodape: str | None = Field(default=None, max_length=300)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    last_login_at: datetime | None


class SessionOut(BaseModel):
    user: UserOut
    tenant: TenantOut
    permissions: list[str]
