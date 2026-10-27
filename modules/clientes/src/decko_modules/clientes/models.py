"""Quem compra da empresa.

Pessoa física ou jurídica, com um documento só: CPF ou CNPJ, conferido pelo dígito e
guardado sem máscara, como no resto do sistema.

O cliente **não é apagado**. Quem comprou aparece em venda, em nota e em trilha de
auditoria; apagar o cadastro deixaria documento apontando para o vazio. O que existe é
desativar, que tira da busca e das telas de lançamento.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Enum, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class TipoPessoa(StrEnum):
    FISICA = "fisica"
    JURIDICA = "juridica"


def _enum(python_enum: type, name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Cliente(TenantMixin, TimestampMixin, Base):
    """Um cliente da empresa."""

    __tablename__ = "clientes_cliente"
    __table_args__ = (
        # Documento é único quando existe. Cliente de balcão sem documento é comum e
        # permitido: exigir CPF para vender um pão travaria a loja.
        UniqueConstraint("tenant_id", "cpf_cnpj", name="uq_clientes_cliente_cpf_cnpj"),
        Index("ix_clientes_cliente_tenant_id_nome", "tenant_id", "nome"),
        Index("ix_clientes_cliente_tenant_id_ativo", "tenant_id", "ativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()

    tipo: Mapped[TipoPessoa] = mapped_column(
        _enum(TipoPessoa, "clientes_tipo_pessoa"), nullable=False, default=TipoPessoa.FISICA
    )
    # Nome da pessoa ou razão social da empresa. Um campo só: a distinção é do tipo, e
    # duas colunas sempre acabam com uma delas vazia.
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # Nome de fantasia, para empresa. A nota sai com a razão social; o balcão chama pelo
    # fantasia, e procurar por ele é o que o vendedor faz.
    apelido: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Só os dígitos, conferidos pelo dígito verificador.
    cpf_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    # Inscrição estadual, para empresa. "ISENTO" é resposta válida e por isso é texto.
    inscricao_estadual: Mapped[str | None] = mapped_column(String(40), nullable=True)

    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Endereço em campos separados, e não em texto livre, porque é o que a nota fiscal
    # exige um dia e o que permite achar cliente por cidade.
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)

    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Desativado some da busca e das telas de lançamento, mas continua existindo para os
    # documentos que já o citam.
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


TENANT_SCOPED_TABLES = (Cliente.__tablename__,)
