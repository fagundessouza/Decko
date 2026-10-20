import uuid

from pydantic import BaseModel, ConfigDict, Field


class ClientIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    # Só dígitos: a formatação é da interface, não do armazenamento.
    cpf_cnpj: str = Field(min_length=11, max_length=14, pattern=r"^\d+$")
    telefone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    cpf_cnpj: str
    telefone: str | None
    email: str | None


class AircraftIn(BaseModel):
    prefixo: str = Field(min_length=1, max_length=20)
    modelo: str | None = Field(default=None, max_length=120)
    fabricante: str | None = Field(default=None, max_length=120)


class AircraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prefixo: str
    modelo: str | None
    fabricante: str | None
    is_active: bool
