import uuid
from datetime import datetime
from typing import Annotated, Any

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


class ModuleOut(BaseModel):
    """Um módulo disponível na plataforma, com o estado dele nesta empresa."""

    name: str
    label: str
    version: str
    # Obrigatório não pode ser desativado e vale como ativo sempre.
    required: bool
    active: bool
    # Como aparece na vitrine. Vem do manifesto do módulo, não de uma lista na interface.
    category: str
    summary: str
    icon: str
    # Cor de identidade na vitrine. Nome do papel; o valor está nos tokens.
    accent: str
    # O que o módulo precisa que já esteja instalado. A vitrine avisa antes de instalar.
    depends: list[str]
    # Se o módulo traz itens iniciais. A empresa que o instalou antes de a semente existir
    # não os tem, e a vitrine é onde ela pede — ver ADR 0010, decisão 3.
    has_seed: bool = False


class SeedResultOut(BaseModel):
    """O que a carga de itens iniciais acrescentou.

    Devolve os identificadores, e não só a contagem, para a conferência saber **o que**
    entrou. A tela mostra o número, porque ``comercial.unidade.un`` não é frase para quem
    opera uma loja.
    """

    module: str
    created: list[str]


class AuditEntryOut(BaseModel):
    """Uma linha da trilha, como a tela de consulta a mostra.

    ``action`` sai como está — ``auth.login.failed`` — e quem traduz para o português é a
    interface. Texto de tela no servidor obrigaria a soltar versão do servidor para
    corrigir uma palavra, e a interface precisa mesmo de um padrão para ação que ela ainda
    não conhece.
    """

    id: uuid.UUID
    action: str
    entity: str
    entity_id: str | None
    data: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime
    user_id: uuid.UUID | None
    # Nulo quando a ação não teve autor, ou quando o usuário foi removido depois: a chave
    # estrangeira é SET NULL, e a trilha sobrevive a quem a gerou.
    author: str | None


class AuditPageOut(BaseModel):
    """Uma página da trilha, com o total para a tela saber o tamanho do histórico."""

    total: int
    entries: list[AuditEntryOut]


class ProfileOut(BaseModel):
    """Um segmento que a plataforma sabe configurar.

    É um conjunto de módulos, não um vínculo: a empresa não "é" de um segmento, ela tem
    módulos ativos — ver docs/adr/0005-perfil-de-segmento.md.
    """

    name: str
    label: str
    description: str
    modules: list[str]
    active: bool


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
    # Módulos ativos nesta empresa. A interface monta o menu a partir daqui: ter a
    # permissão de um módulo não significa que a empresa o contratou.
    active_modules: list[str]
