import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
