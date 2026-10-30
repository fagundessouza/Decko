import uuid

from pydantic import BaseModel, ConfigDict, Field


class ContaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    instituicao: str | None = Field(default=None, max_length=120)
    # Texto livre: chave Pix é CPF, CNPJ, e-mail, telefone ou aleatória.
    chave_pix: str | None = Field(default=None, max_length=200)


class ContaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    instituicao: str | None
    chave_pix: str | None
    ativa: bool
