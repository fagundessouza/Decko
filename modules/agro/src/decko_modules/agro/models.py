"""Modelo de dados da pulverização agrícola.

Cada tabela corresponde a uma seção do formulário "Planejamento Operacional" exigido pelo
MAPA, hoje preenchido em talão de papel. O mapa campo a campo está em
``docs/discovery/agro-planejamento-operacional.md``; nada aqui foi inventado.

Nomes de tabela levam o prefixo ``agro_`` para que módulos diferentes possam coexistir no
mesmo schema sem disputar nomes.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin, primary_key
from decko_modules.agro.enums import (
    Cultura,
    EquipamentoTipo,
    MaintenanceMoment,
    Momento,
    Periodo,
    PlanStatus,
    SignatureRole,
    TipoAplicacao,
    WeatherSource,
)


def _enum(python_enum: type, name: str) -> Enum:
    """Enum nativo do PostgreSQL guardando o valor, não o nome do membro."""
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class Client(TenantMixin, TimestampMixin, Base):
    """Contratante do serviço de pulverização."""

    __tablename__ = "agro_client"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cpf_cnpj", name="uq_agro_client_tenant_id_cpf_cnpj"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    properties: Mapped[list["Property"]] = relationship(back_populates="client")


class Property(TenantMixin, TimestampMixin, Base):
    """Propriedade rural onde a aplicação acontece.

    As coordenadas são guardadas em grau decimal e convertidas para grau/minuto/segundo
    apenas na emissão do documento, que é o formato que o formulário exige.
    """

    __tablename__ = "agro_property"

    id: Mapped[uuid.UUID] = primary_key()
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agro_client.id", ondelete="RESTRICT"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    municipio: Mapped[str] = mapped_column(String(120), nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="properties")


class Aircraft(TenantMixin, TimestampMixin, Base):
    """Drone ou avião agrícola."""

    __tablename__ = "agro_aircraft"
    __table_args__ = (
        UniqueConstraint("tenant_id", "prefixo", name="uq_agro_aircraft_tenant_id_prefixo"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    prefixo: Mapped[str] = mapped_column(String(20), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fabricante: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Pilot(TenantMixin, TimestampMixin, Base):
    """Piloto agrícola da empresa.

    Pedido do Nathan em 27/10/2026: *"uma forma da empresa cadastrar os pilotos, cada um
    fazia seu relatório"*. Antes o nome do piloto só existia como texto dentro da
    assinatura, redigitado a cada documento.

    O CREA é opcional e existe porque na AgroDrone **a mesma pessoa é o agrônomo e o
    piloto** — os quatro papéis de assinatura do formulário não são quatro pessoas.
    """

    __tablename__ = "agro_pilot"
    __table_args__ = (UniqueConstraint("tenant_id", "canac", name="uq_agro_pilot_tenant_id_canac"),)

    id: Mapped[uuid.UUID] = primary_key()
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # Código ANAC do aeronavegante. É o registro que o formulário imprime ao lado da
    # assinatura do piloto.
    canac: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Preenchido quando o piloto também assina como engenheiro agrônomo.
    crea: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(TenantMixin, TimestampMixin, Base):
    """Defensivo, adjuvante ou fertilizante aplicado."""

    __tablename__ = "agro_product"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "nome_comercial", name="uq_agro_product_tenant_id_nome_comercial"
        ),
    )

    id: Mapped[uuid.UUID] = primary_key()
    nome_comercial: Mapped[str] = mapped_column(String(200), nullable=False)
    formulacao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    classe_toxicologica: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registro_mapa: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_adjuvante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Prescription(TenantMixin, TimestampMixin, Base):
    """Receituário agronômico.

    O formulário remete as precauções de uso a este documento, então o vínculo é parte do
    registro legal, não um anexo opcional.
    """

    __tablename__ = "agro_prescription"
    __table_args__ = (
        UniqueConstraint("tenant_id", "numero", name="uq_agro_prescription_tenant_id_numero"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    numero: Mapped[str] = mapped_column(String(60), nullable=False)
    emitido_em: Mapped[date] = mapped_column(Date, nullable=False)
    agronomo_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    agronomo_crea: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Chave do objeto no armazenamento. O armazenamento em si entra em fase posterior.
    arquivo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)


class OperationalPlan(TenantMixin, TimestampMixin, Base):
    """Planejamento Operacional: o documento que o MAPA exige por aplicação."""

    __tablename__ = "agro_operational_plan"
    __table_args__ = (
        UniqueConstraint("tenant_id", "numero", name="uq_agro_operational_plan_tenant_id_numero"),
        Index("ix_agro_operational_plan_tenant_id_data", "tenant_id", "data_aplicacao"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    # Sequencial por empresa, impresso no cabeçalho do talão.
    numero: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus, "agro_plan_status"), nullable=False, default=PlanStatus.RASCUNHO
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agro_client.id", ondelete="RESTRICT"), nullable=False
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agro_property.id", ondelete="RESTRICT"), nullable=False
    )
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agro_aircraft.id", ondelete="RESTRICT"), nullable=True
    )
    # Quem voou. Opcional porque o documento antigo não tem, e porque a empresa de um
    # piloto só pode nunca cadastrar ninguém.
    pilot_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agro_pilot.id", ondelete="RESTRICT"), nullable=True
    )
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agro_prescription.id", ondelete="RESTRICT"),
        nullable=True,
    )

    data_aplicacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    cotacao: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Coordenadas da área efetivamente aplicada. Podem diferir da sede da propriedade.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    cultura: Mapped[Cultura | None] = mapped_column(_enum(Cultura, "agro_cultura"), nullable=True)
    cultura_outras_texto: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # O formulário permite marcar mais de um tipo na mesma aplicação.
    tipos_aplicacao: Mapped[list[TipoAplicacao] | None] = mapped_column(
        ARRAY(_enum(TipoAplicacao, "agro_tipo_aplicacao")), nullable=True
    )
    tipo_outros_texto: Mapped[str | None] = mapped_column(String(120), nullable=True)
    area_ha: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    equipamento_tipo: Mapped[EquipamentoTipo | None] = mapped_column(
        _enum(EquipamentoTipo, "agro_equipamento_tipo"), nullable=True
    )
    equipamento_modelo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    equipamento_bico_tipo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    equipamento_bico_angulo: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Limites planejados pelo responsável técnico. São o que define se uma leitura
    # meteorológica configura risco de deriva.
    param_temperatura_maxima_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    param_umidade_relativa_min_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    param_velocidade_vento_max_kmh: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    param_largura_faixa_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    param_altura_voo_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    tempo_servico: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    ha_aplicado: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    emitiu_relatorio_dgps: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    termo_higrometro_utilizado: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # O formulário exige o croqui com direção dos tiros e sentido do vento em anexo.
    croqui_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    products: Mapped[list["PlanProduct"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    weather_readings: Mapped[list["WeatherReading"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    signatures: Mapped[list["Signature"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanProduct(TenantMixin, Base):
    """Uma linha da tabela de produtos do formulário.

    ``formulacao`` e ``classe_toxicologica`` são copiadas do cadastro no momento da
    emissão. Referenciá-las faria um documento já emitido mudar de conteúdo quando o
    cadastro fosse corrigido, o que é inaceitável em registro com efeito legal.
    """

    __tablename__ = "agro_plan_product"

    id: Mapped[uuid.UUID] = primary_key()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agro_operational_plan.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agro_product.id", ondelete="RESTRICT"), nullable=False
    )

    formulacao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    classe_toxicologica: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dosagem_ha: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    volume_ha: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    total_produto: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    adjuvante: Mapped[str | None] = mapped_column(String(200), nullable=True)

    plan: Mapped["OperationalPlan"] = relationship(back_populates="products")


class MaintenanceLog(TenantMixin, Base):
    """Bloco "Controle de Manutenção (Horas x Voo)" do formulário."""

    __tablename__ = "agro_maintenance_log"
    __table_args__ = (
        UniqueConstraint("plan_id", "momento", name="uq_agro_maintenance_log_plan_id_momento"),
    )

    id: Mapped[uuid.UUID] = primary_key()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agro_operational_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    momento: Mapped[MaintenanceMoment] = mapped_column(
        _enum(MaintenanceMoment, "agro_maintenance_moment"), nullable=False
    )
    voo: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    translado_ida: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    operacao: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    translado_volta: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    plan: Mapped["OperationalPlan"] = relationship(back_populates="maintenance_logs")


class WeatherReading(TenantMixin, Base):
    """Leitura meteorológica no momento da aplicação.

    É o registro mais sensível do documento. Aplicar com vento fora da janela causa deriva
    sobre a lavoura vizinha, e disso nascem processos. Hoje essas leituras são anotadas de
    memória depois do voo, o que não constitui prova.

    Por isso ``source``, ``provider`` e ``payload_bruto`` são guardados junto do valor: o
    que torna a leitura defensável não é o número, é a origem dele.
    """

    __tablename__ = "agro_weather_reading"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "data",
            "periodo",
            "momento",
            name="uq_agro_weather_reading_plan_id_data_periodo_momento",
        ),
    )

    id: Mapped[uuid.UUID] = primary_key()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agro_operational_plan.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    data: Mapped[date] = mapped_column(Date, nullable=False)
    periodo: Mapped[Periodo] = mapped_column(_enum(Periodo, "agro_periodo"), nullable=False)
    momento: Mapped[Momento] = mapped_column(_enum(Momento, "agro_momento"), nullable=False)
    hora: Mapped[time | None] = mapped_column(Time, nullable=True)

    temperatura_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    umidade_relativa_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    velocidade_vento_kmh: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    source: Mapped[WeatherSource] = mapped_column(
        _enum(WeatherSource, "agro_weather_source"), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Resposta íntegra do provedor, preservada como evidência pericial.
    payload_bruto: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Derivado na gravação, comparando com os parâmetros do planejamento.
    violou_parametro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    plan: Mapped["OperationalPlan"] = relationship(back_populates="weather_readings")


class Signature(TenantMixin, Base):
    """Uma das quatro assinaturas exigidas pelo formulário.

    Cada papel traz seu registro profissional próprio: CREA para agrônomo e técnico,
    CANAC para o piloto, CPF para o proprietário.
    """

    __tablename__ = "agro_signature"
    __table_args__ = (UniqueConstraint("plan_id", "papel", name="uq_agro_signature_plan_id_papel"),)

    id: Mapped[uuid.UUID] = primary_key()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agro_operational_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    papel: Mapped[SignatureRole] = mapped_column(
        _enum(SignatureRole, "agro_signature_role"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    registro: Mapped[str | None] = mapped_column(String(60), nullable=True)
    assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["OperationalPlan"] = relationship(back_populates="signatures")


# Lidas pela migração para aplicar Row Level Security. Uma tabela nova com tenant_id que
# não apareça aqui fica sem política, e o teste de isolamento do módulo acusa.
TENANT_SCOPED_TABLES = (
    Client.__tablename__,
    Property.__tablename__,
    Aircraft.__tablename__,
    Pilot.__tablename__,
    Product.__tablename__,
    Prescription.__tablename__,
    OperationalPlan.__tablename__,
    PlanProduct.__tablename__,
    MaintenanceLog.__tablename__,
    WeatherReading.__tablename__,
    Signature.__tablename__,
)
