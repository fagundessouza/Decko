import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from decko_modules.assinaturas.models import Acesso, StatusAssinatura, StatusCobranca


class PlanoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    preco_mensal: Decimal = Field(ge=0)
    descricao: str | None = Field(default=None, max_length=400)


class PlanoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    descricao: str | None
    preco_mensal: Decimal
    ativo: bool


class AssinaturaIn(BaseModel):
    cliente_id: uuid.UUID
    plano_id: uuid.UUID
    inicio: date
    # Até 28 para existir em fevereiro.
    dia_vencimento: int = Field(default=10, ge=1, le=28)


class CobrancaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    competencia: date
    valor: Decimal
    vencimento: date
    status: StatusCobranca
    pago_em: date | None
    forma_pagamento: str | None

    prazo_ate: date | None
    prazo_motivo: str | None
    # O último dia antes do bloqueio, já com o prazo de confiança somado. Vem calculado do
    # servidor: a tela não refaz regra de cobrança.
    bloqueia_em: date


class AssinaturaOut(BaseModel):
    """A assinatura como a tela a mostra, com o estado de acesso já resolvido."""

    id: uuid.UUID
    cliente_id: uuid.UUID
    # Lido na hora, não copiado: corrigir um nome vale para as assinaturas da pessoa.
    cliente_nome: str
    plano_id: uuid.UUID
    plano_nome: str
    status: StatusAssinatura
    inicio: date
    dia_vencimento: int

    # Derivado da cobrança mais antiga em aberto e da data de hoje — nunca uma coluna.
    # Ver docs/adr/0013-assinatura-recorrente.md, decisão 3.
    acesso: Acesso
    em_aberto: Decimal
    cobrancas: list[CobrancaOut]


class BaixaIn(BaseModel):
    pago_em: date
    forma_pagamento: str | None = Field(default=None, max_length=40)


class PrazoIn(BaseModel):
    ate: date
    # Obrigatório: sem motivo, daqui a três meses ninguém sabe por que houve prazo.
    motivo: str = Field(min_length=1, max_length=300)


class CompetenciaIn(BaseModel):
    ano: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)


class GeracaoOut(BaseModel):
    """O que a geração do mês criou. Zero é resposta: já estava gerado."""

    competencia: date
    criadas: int
