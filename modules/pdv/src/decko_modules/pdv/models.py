"""Ponto de venda: a venda de balcão e o que ela movimenta.

O PDV não tem cadastro próprio de produto, de estoque nem de cliente: usa os dos módulos
``comercial`` e ``clientes``, que ele declara em ``depends`` — ver
``docs/adr/0007-dependencia-entre-modulos.md``.

O que ficou de fora de propósito, e por quê, está em ``docs/adr/0008-ponto-de-venda.md``.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key


class StatusVenda(StrEnum):
    ABERTA = "aberta"
    FINALIZADA = "finalizada"
    CANCELADA = "cancelada"


class FormaPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    DEBITO = "debito"
    CREDITO = "credito"
    PIX = "pix"
    # Vale-refeição, convênio, o que a loja aceitar. Existe para a venda não travar por
    # falta de uma opção; a lista fechada vem com o módulo fiscal, que tem a tabela certa.
    OUTRO = "outro"


class TipoMovimentoCaixa(StrEnum):
    SANGRIA = "sangria"
    SUPRIMENTO = "suprimento"


class AcaoAutorizada(StrEnum):
    """O que o operador não faz sozinho quando a loja exige supervisor.

    Decisão e motivos: ``docs/adr/0020-operador-supervisor-e-papeis.md``, decisão 4.
    """

    CANCELAR_ITEM = "cancelar_item"
    CANCELAR_VENDA = "cancelar_venda"
    SANGRIA = "sangria"
    DEVOLUCAO = "devolucao"
    DESCONTO = "desconto"
    FECHAR_CAIXA = "fechar_caixa"


class DestinoDevolucao(StrEnum):
    """Para onde vai o produto que o cliente trouxe de volta.

    São dois e só dois, e a diferença é se aquilo pode ser vendido de novo. Não existe
    depósito de avaria: o que tem defeito simplesmente **não entra** no estoque vendável,
    e é isso que mantém o saldo dizendo a verdade sobre o que dá para vender. Ver a
    atualização de 10/11/2026 da ``docs/adr/0008-ponto-de-venda.md``.
    """

    ESTOQUE = "estoque"
    AVARIA = "avaria"


def _enum(python_enum: type, name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Contador(Base):
    """O próximo número de venda de cada empresa.

    Uma linha por empresa, incrementada em ``INSERT ... ON CONFLICT DO UPDATE RETURNING``:
    é o banco que serializa dois caixas fechando junto, e não a aplicação. Contar
    ``max(numero) + 1`` daria o mesmo número aos dois.

    Não usa ``TenantMixin`` porque aqui a empresa é a própria chave primária — uma coluna
    de identidade artificial permitiria duas linhas para a mesma empresa, que é
    exatamente o que não pode existir.
    """

    __tablename__ = "pdv_contador"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    )
    proximo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Venda(TenantMixin, TimestampMixin, Base):
    """Uma venda de balcão.

    ``numero`` só é atribuído ao finalizar: enquanto aberta a venda é identificada pelo
    id. Numerar na abertura gastaria número em venda abandonada, e o número é o que o
    cliente vê no cupom.
    """

    __tablename__ = "pdv_venda"
    __table_args__ = (
        UniqueConstraint("tenant_id", "numero", name="uq_pdv_venda_tenant_id_numero"),
        Index("ix_pdv_venda_tenant_id_status", "tenant_id", "status"),
        Index("ix_pdv_venda_tenant_id_fechada_em", "tenant_id", "fechada_em"),
        CheckConstraint("desconto >= 0", name="desconto_nao_negativo"),
        CheckConstraint("total IS NULL OR total >= 0", name="total_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[StatusVenda] = mapped_column(
        _enum(StatusVenda, "pdv_status_venda"), nullable=False, default=StatusVenda.ABERTA
    )

    # Desconto sobre a venda inteira, além do que cada item possa ter.
    desconto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal(0))

    # Congelado ao finalizar. Enquanto a venda está aberta o total é a soma dos itens, que
    # ainda muda; depois de fechada ele é o que o cliente pagou, e não pode acompanhar uma
    # mudança de preço do produto no cadastro.
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    aberta_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    operador_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    # Quem comprou, quando a venda é identificada. Nulo é o caso normal: exigir CPF para
    # vender um pão travaria o balcão.
    #
    # `RESTRICT` e não `SET NULL`: o cadastro de clientes nunca apaga, só desativa,
    # justamente para a venda continuar apontando para alguém. Aqui o banco cobra essa
    # promessa. Ver a atualização de 29/10/2026 em docs/adr/0008-ponto-de-venda.md.
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes_cliente.id", ondelete="RESTRICT"),
        nullable=True,
    )
    observacao: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Em qual sessão de caixa esta venda foi fechada. Nulo quando o operador não tinha
    # caixa aberto — e **continua nulo**: abrir o caixa depois não puxa para dentro dele o
    # que foi vendido antes, senão o fechamento mentiria sobre o próprio período. Ver a
    # atualização de 10/11/2026 na docs/adr/0008-ponto-de-venda.md.
    caixa_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pdv_caixa.id", ondelete="RESTRICT"),
        nullable=True,
    )

    itens: Mapped[list["ItemVenda"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan", order_by="ItemVenda.created_at"
    )
    pagamentos: Mapped[list["Pagamento"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan", order_by="Pagamento.created_at"
    )


class ItemVenda(TenantMixin, TimestampMixin, Base):
    """Uma linha da venda.

    ``preco_unitario`` é cópia, não referência: mudar o preço no cadastro amanhã não pode
    mudar o que foi vendido hoje.
    """

    __tablename__ = "pdv_venda_item"
    __table_args__ = (
        Index("ix_pdv_venda_item_venda_id", "venda_id"),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
        CheckConstraint("preco_unitario >= 0", name="preco_nao_negativo"),
        CheckConstraint("desconto >= 0", name="desconto_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    venda_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_venda.id", ondelete="CASCADE"), nullable=False
    )

    # Do módulo comercial. A chave estrangeira existe porque é o banco que garante que o
    # produto não some debaixo de uma venda já fechada.
    produto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_produto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lote_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comercial_lote.id", ondelete="RESTRICT"), nullable=True
    )
    unidade_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comercial_unidade.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Na unidade digitada: vender "2 caixas" é guardado como 2, com a unidade caixa. A
    # conversão para a unidade base acontece na baixa de estoque, no módulo comercial.
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    desconto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal(0))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Cópia do nome no momento da venda, pelo mesmo motivo do preço: o cupom reimpresso
    # precisa dizer o que foi vendido, não o que o produto se chama hoje.
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)

    venda: Mapped["Venda"] = relationship(back_populates="itens")


class Pagamento(TenantMixin, TimestampMixin, Base):
    """Uma forma de pagamento usada na venda. Uma venda pode ter várias."""

    __tablename__ = "pdv_pagamento"
    __table_args__ = (
        Index("ix_pdv_pagamento_venda_id", "venda_id"),
        CheckConstraint("valor > 0", name="valor_positivo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    venda_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_venda.id", ondelete="CASCADE"), nullable=False
    )
    forma: Mapped[FormaPagamento] = mapped_column(
        _enum(FormaPagamento, "pdv_forma_pagamento"), nullable=False
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Em qual conta o dinheiro caiu. A forma diz **como** o cliente pagou; isto diz
    # **onde** — e é a segunda pergunta que não fecha no fim do dia, porque duas chaves Pix
    # da mesma loja são dois destinos.
    #
    # Nulo por padrão, e nada no caixa trava por causa dele: velocidade de balcão é
    # requisito. Ver docs/adr/0014-conta-de-recebimento.md, decisão 3.
    conta_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financeiro_conta.id", ondelete="RESTRICT"),
        nullable=True,
    )

    venda: Mapped["Venda"] = relationship(back_populates="pagamentos")


class Caixa(TenantMixin, TimestampMixin, Base):
    """Uma sessão de caixa: o que passou pelas mãos de um operador, entre abrir e fechar.

    Pertence ao **operador**, não à máquina — ver a atualização de 10/11/2026 na
    ``docs/adr/0008-ponto-de-venda.md``. Não existe entidade de terminal, e esta tabela
    não cria uma.

    Aberto ou fechado é **derivado** de ``fechado_em``, não guardado em coluna: estado que
    se calcula não diverge do fato que o produziu. Mesmo princípio da ADR 0013.
    """

    __tablename__ = "pdv_caixa"

    id: Mapped[uuid.UUID] = primary_key()
    operador_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=False
    )

    aberto_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # O fundo de troco com que a gaveta começou.
    abertura: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Preenchidos no fechamento, e só lá. São fato histórico — o que foi contado, o que se
    # esperava naquele instante e a diferença —, por isso viram coluna. O esperado de uma
    # sessão aberta é conta feita na leitura, e não se guarda.
    contado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    esperado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    diferenca: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # Um operador não tem dois caixas abertos ao mesmo tempo. O índice parcial é o que
        # faz o banco recusar, e não a aplicação: duas abas abertas tentariam as duas.
        Index(
            "uq_pdv_caixa_aberto_por_operador",
            "tenant_id",
            "operador_id",
            unique=True,
            postgresql_where=text("fechado_em IS NULL"),
        ),
        CheckConstraint("abertura >= 0", name="ck_pdv_caixa_abertura_nao_negativa"),
    )


class MovimentoCaixa(TenantMixin, TimestampMixin, Base):
    """Dinheiro que entra ou sai da gaveta fora de venda.

    Sem isto o esperado nunca bate numa loja que faz retirada durante o dia — e um número
    que nunca bate deixa de ser conferido na segunda semana.
    """

    __tablename__ = "pdv_caixa_movimento"

    id: Mapped[uuid.UUID] = primary_key()
    caixa_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_caixa.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[TipoMovimentoCaixa] = mapped_column(
        _enum(TipoMovimentoCaixa, "pdv_tipo_movimento_caixa"), nullable=False
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Por que o dinheiro saiu. Sangria sem motivo é a linha que ninguém consegue explicar
    # depois, e é justamente a que importa explicar.
    motivo: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (CheckConstraint("valor > 0", name="ck_pdv_caixa_movimento_valor_positivo"),)


class Devolucao(TenantMixin, TimestampMixin, Base):
    """O que o cliente trouxe de volta, e quanto recebeu por isso.

    É **documento novo**, nunca edição da venda: a venda continua ``finalizada``, com o
    mesmo total e os mesmos preços, porque o cupom precisa seguir dizendo o que o cliente
    pagou. "Devolvida" não é status da venda — é a soma das devoluções dela, feita na
    leitura. Mesmo princípio da ADR 0013.

    O estoque segue a mesma lógica: a razão do módulo comercial não aceita edição do
    passado, então a devolução lança **entrada** e não desfaz a saída da venda.
    """

    __tablename__ = "pdv_devolucao"
    __table_args__ = (
        Index("ix_pdv_devolucao_venda_id", "venda_id"),
        Index("ix_pdv_devolucao_tenant_id_created_at", "tenant_id", "created_at"),
        CheckConstraint("total >= 0", name="ck_pdv_devolucao_total_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()

    # `RESTRICT` e não `CASCADE`: a devolução não é parte da venda, é documento sobre ela.
    # Apagar a venda por baixo de um reembolso já pago não pode ser silencioso.
    venda_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_venda.id", ondelete="RESTRICT"), nullable=False
    )

    operador_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    # Em qual sessão de caixa a devolução caiu. Nulo quando quem registrou não tinha caixa
    # aberto — e continua nulo, pela mesma razão da venda fora de sessão.
    caixa_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_caixa.id", ondelete="RESTRICT"), nullable=True
    )

    # Como o dinheiro voltou. Só `dinheiro` mexe no esperado da gaveta; cartão e Pix ficam
    # registrados na forma original, porque o estorno é da adquirente e não do sistema.
    forma: Mapped[FormaPagamento] = mapped_column(
        _enum(FormaPagamento, "pdv_forma_pagamento"), nullable=False
    )

    # Obrigatório, pela razão da sangria: devolução que ninguém explica depois é justamente
    # a que importa explicar.
    motivo: Mapped[str] = mapped_column(String(300), nullable=False)

    # Soma das linhas, calculada no servidor. Ver a atualização de 10/11/2026 da ADR 0008:
    # valor de reembolso digitado à mão é onde a fraude mora.
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    itens: Mapped[list["ItemDevolucao"]] = relationship(
        back_populates="devolucao",
        cascade="all, delete-orphan",
        order_by="ItemDevolucao.created_at",
    )


class ItemDevolucao(TenantMixin, TimestampMixin, Base):
    """Uma linha da venda voltando, inteira ou em parte.

    Aponta para o item da venda, e não para o produto: é a linha vendida que está sendo
    desfeita, com o preço e a unidade daquele momento. Duas linhas para o mesmo item da
    venda são válidas e esperadas — três garrafas voltam ao estoque e uma quebrou.
    """

    __tablename__ = "pdv_devolucao_item"
    __table_args__ = (
        Index("ix_pdv_devolucao_item_devolucao_id", "devolucao_id"),
        # Usado para somar o que cada linha da venda já devolveu, que é o limite.
        Index("ix_pdv_devolucao_item_venda_item_id", "venda_item_id"),
        CheckConstraint("quantidade > 0", name="ck_pdv_devolucao_item_quantidade_positiva"),
        CheckConstraint("valor >= 0", name="ck_pdv_devolucao_item_valor_nao_negativo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    devolucao_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_devolucao.id", ondelete="CASCADE"), nullable=False
    )
    venda_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pdv_venda_item.id", ondelete="RESTRICT"), nullable=False
    )

    # Na mesma unidade em que foi vendida: devolver "1 caixa" de uma venda em caixas.
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Quanto desta linha voltou em dinheiro, já com o fator do desconto da venda.
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    destino: Mapped[DestinoDevolucao] = mapped_column(
        _enum(DestinoDevolucao, "pdv_destino_devolucao"), nullable=False
    )

    devolucao: Mapped["Devolucao"] = relationship(back_populates="itens")


class ConfiguracaoPdv(Base):
    """O que esta loja exige autorização para fazer, e a partir de quanto.

    Uma linha por empresa, com a empresa como chave primária — mesmo motivo do
    ``Contador``: uma identidade artificial permitiria duas linhas para a mesma loja, que
    é exatamente o que não pode existir.

    **As quatro exigências que o dono do projeto escolheu nascem ligadas.** As duas que
    dependem de um número — desconto e diferença no fechamento — nascem **desligadas**,
    porque ligá-las exige escolher o limite, e inventar esse limite seria inventar regra
    de negócio (``CLAUDE.md``, regra 6).
    """

    __tablename__ = "pdv_configuracao"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    )

    exige_cancelar_item: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exige_cancelar_venda: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exige_sangria: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exige_devolucao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    exige_desconto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Até quanto o operador desconta sozinho. Zero com a exigência ligada quer dizer
    # "qualquer desconto precisa de supervisor".
    desconto_livre: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal(0)
    )

    exige_diferenca: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Quanto de diferença o fechamento aceita sem supervisor, para mais ou para menos.
    # É a única trava deste tipo que o Odoo tem de fábrica (*Set Maximum Difference*).
    diferenca_livre: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal(0)
    )

    __table_args__ = (
        CheckConstraint("desconto_livre >= 0", name="ck_pdv_configuracao_desconto_livre"),
        CheckConstraint("diferenca_livre >= 0", name="ck_pdv_configuracao_diferenca_livre"),
    )


class Autorizacao(TenantMixin, TimestampMixin, Base):
    """Uma liberação dada por quem podia, para alguém que não podia sozinho.

    Guarda **as duas pessoas**: uma linha que diz só "sangria de R$ 200" não responde nada
    numa investigação, e é por causa dessa pergunta que esta tabela existe.

    Só existe linha quando a autorização foi **concedida**. Não há coluna de estado: o
    pedido que o chefe libera à distância precisa de um canal de notificação que o projeto
    não tem, e uma coluna com um valor só seria ruído — ``CLAUDE.md``, "não crie abstração
    para caso hipotético". Ver ``docs/adr/0020-operador-supervisor-e-papeis.md``.
    """

    __tablename__ = "pdv_autorizacao"

    id: Mapped[uuid.UUID] = primary_key()
    acao: Mapped[AcaoAutorizada] = mapped_column(
        _enum(AcaoAutorizada, "pdv_acao_autorizada"), nullable=False
    )

    # Quem pediu. `SET NULL` porque a linha é histórico e não pode sumir com a pessoa.
    solicitante_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    # Quem liberou. Também `SET NULL`, pelo mesmo motivo — e o nome de quem liberou é lido
    # do cadastro na hora de mostrar, não copiado.
    autorizador_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    # A que a liberação se refere: id da venda, do caixa, do que for. Texto, e não chave
    # estrangeira, porque uma só coluna aponta para tabelas diferentes conforme a ação.
    referencia: Mapped[str | None] = mapped_column(String(80), nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        Index("ix_pdv_autorizacao_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_pdv_autorizacao_autorizador_id", "autorizador_id"),
    )


TENANT_SCOPED_TABLES = (
    Contador.__tablename__,
    Venda.__tablename__,
    ItemVenda.__tablename__,
    Pagamento.__tablename__,
    Caixa.__tablename__,
    MovimentoCaixa.__tablename__,
    Devolucao.__tablename__,
    ItemDevolucao.__tablename__,
    Autorizacao.__tablename__,
    ConfiguracaoPdv.__tablename__,
)
