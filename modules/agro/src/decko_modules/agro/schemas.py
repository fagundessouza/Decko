import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field

from decko.documents import pydantic_cpf_cnpj
from decko_modules.agro.enums import (
    Cultura,
    Momento,
    Periodo,
    PlanStatus,
    SignatureRole,
    TipoAplicacao,
)


class ClientIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    # Guardado sem máscara e conferido pelo dígito verificador: ver decko.documents.
    # O documento identifica o contratante num registro com efeito legal, então entrar
    # errado aqui sai errado no papel que vai para a fiscalização.
    cpf_cnpj: Annotated[str, BeforeValidator(pydantic_cpf_cnpj)]
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
    #: O série do equipamento, que é o que casa com o registro de voo importado. O apelido
    #: que aparece no aplicativo não serve: quem identifica a ARP para o MAPA é o prefixo.
    numero_serie: str | None = Field(default=None, max_length=60)


class AircraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prefixo: str
    modelo: str | None
    fabricante: str | None
    numero_serie: str | None
    is_active: bool


class PilotIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    # Código ANAC do aeronavegante, impresso ao lado da assinatura do piloto.
    canac: str | None = Field(default=None, max_length=20)
    # Preenchido quando o piloto também assina como engenheiro agrônomo — na AgroDrone é
    # a mesma pessoa.
    crea: str | None = Field(default=None, max_length=40)
    cpf: str | None = Field(default=None, max_length=14)
    telefone: str | None = Field(default=None, max_length=20)


class PilotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    canac: str | None
    crea: str | None
    cpf: str | None
    telefone: str | None
    is_active: bool


class PropertyIn(BaseModel):
    client_id: uuid.UUID
    nome: str = Field(min_length=1, max_length=200)
    municipio: str = Field(min_length=1, max_length=120)
    uf: str = Field(min_length=2, max_length=2)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    nome: str
    municipio: str
    uf: str
    latitude: Decimal | None
    longitude: Decimal | None


class PlanIn(BaseModel):
    """O planejamento como ele chega. A identidade pode vir do aparelho.

    `id` é opcional e existe para o planejamento preenchido **sem rede**: o aparelho
    escolhe a identidade, e reenviar o mesmo pacote devolve o que já está aqui em vez de
    criar um segundo planejamento com outro número. É a decisão 2 da
    `docs/adr/0019-offline-first.md`, a mesma já usada no cadastro de cliente e na venda
    de balcão. Quem está online não manda nada: o servidor gera, como sempre fez.
    """

    id: uuid.UUID | None = None
    client_id: uuid.UUID
    property_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    # Quem voou. Antes o nome do piloto só existia dentro da assinatura.
    pilot_id: uuid.UUID | None = None
    # O formulário remete as precauções de uso ao receituário. Fica opcional aqui porque
    # o planejamento nasce rascunho, antes de o receituário estar em mãos.
    prescription_id: uuid.UUID | None = None
    data_aplicacao: date | None = None
    cultura: Cultura | None = None
    cultura_outras_texto: str | None = Field(default=None, max_length=120)
    tipos_aplicacao: list[TipoAplicacao] | None = None
    area_ha: Decimal | None = Field(default=None, ge=0)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    # Limites da aplicação. São o que transforma uma leitura meteorológica em alerta.
    param_temperatura_maxima_c: Decimal | None = None
    param_umidade_relativa_min_pct: Decimal | None = Field(default=None, ge=0, le=100)
    param_velocidade_vento_max_kmh: Decimal | None = Field(default=None, ge=0)
    param_largura_faixa_m: Decimal | None = Field(default=None, ge=0)
    param_altura_voo_m: Decimal | None = Field(default=None, ge=0)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int
    status: PlanStatus
    client_id: uuid.UUID
    property_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    pilot_id: uuid.UUID | None
    prescription_id: uuid.UUID | None
    data_aplicacao: date | None
    cultura: Cultura | None
    area_ha: Decimal | None
    param_temperatura_maxima_c: Decimal | None
    param_umidade_relativa_min_pct: Decimal | None
    param_velocidade_vento_max_kmh: Decimal | None


class WeatherCaptureIn(BaseModel):
    data: date
    periodo: Periodo
    momento: Momento
    # Obrigatório: só quem voou sabe a hora exata, e inferi-la falsearia o documento.
    hora: time
    # Informadas pelo aparelho em campo; na ausência, caem para o planejamento ou a
    # propriedade.
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class WeatherReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data: date
    periodo: Periodo
    momento: Momento
    hora: time | None
    temperatura_c: Decimal | None
    umidade_relativa_pct: Decimal | None
    velocidade_vento_kmh: Decimal | None
    direcao_vento_graus: Decimal | None
    source: str
    provider: str | None
    captured_at: datetime | None
    violou_parametro: bool


class WeatherCaptureOut(BaseModel):
    leitura: WeatherReadingOut
    # Vazio significa aplicação dentro dos limites planejados.
    alertas: list[str]


class ProductIn(BaseModel):
    nome_comercial: str = Field(min_length=1, max_length=200)
    formulacao: str | None = Field(default=None, max_length=120)
    classe_toxicologica: str | None = Field(default=None, max_length=40)
    registro_mapa: str | None = Field(default=None, max_length=60)
    is_adjuvante: bool = False


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome_comercial: str
    formulacao: str | None
    classe_toxicologica: str | None
    registro_mapa: str | None
    is_adjuvante: bool


class PrescriptionIn(BaseModel):
    numero: str = Field(min_length=1, max_length=60)
    emitido_em: date
    agronomo_nome: str | None = Field(default=None, max_length=200)
    agronomo_crea: str | None = Field(default=None, max_length=40)


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    emitido_em: date
    agronomo_nome: str | None
    agronomo_crea: str | None


class PlanProductIn(BaseModel):
    product_id: uuid.UUID
    dosagem_ha: Decimal | None = Field(default=None, ge=0)
    volume_ha: Decimal | None = Field(default=None, ge=0)
    # Não é derivado de dosagem por área: o talão traz a coluna e o receituário dita o
    # valor. Qual área multiplicar (planejada ou aplicada) é a questão Q9 do discovery.
    total_produto: Decimal | None = Field(default=None, ge=0)
    adjuvante: str | None = Field(default=None, max_length=200)


class PlanProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    # Cópia feita na inclusão da linha, não o valor atual do cadastro.
    formulacao: str | None
    classe_toxicologica: str | None
    dosagem_ha: Decimal | None
    volume_ha: Decimal | None
    total_produto: Decimal | None
    adjuvante: str | None


class PlanPrescriptionIn(BaseModel):
    """Vínculo do receituário feito depois, quando o documento chega às mãos de quem voa."""

    prescription_id: uuid.UUID | None


class ConsolidationPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int
    status: str
    data_aplicacao: date | None
    contratante: str
    contratante_documento: str
    propriedade: str
    municipio: str
    uf: str
    cultura: str
    area_ha: Decimal | None
    aeronave: str
    produtos: list[str]
    leituras: int
    violacoes: int


class ProductTotalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    produto: str
    total: Decimal


class ConsolidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ano: int
    mes: int
    quantidade: int
    area_total_ha: Decimal
    # O número que a empresa precisa ver antes de enviar o mês, não depois da autuação.
    planos_com_violacao: int
    # Planejamento sem data não cabe em mês nenhum; contado para não sumir da conferência.
    planos_sem_data: int
    totais_por_produto: list[ProductTotalOut]
    planos: list[ConsolidationPlanOut]


class MonthlyReportRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    municipio: str
    uf: str
    aeronave: str
    tipo_atividade: str
    area_ha: Decimal
    horas: Decimal
    # "marca comercial, volume e dosagem aplicada", do inciso V, já montado para leitura.
    produtos: list[str]


class MonthlyReportOut(BaseModel):
    """O relatório mensal do operador de ARP — Portaria MAPA 298/2021, art. 11."""

    ano: int
    mes: int
    linhas: list[MonthlyReportRowOut]
    area_total_ha: Decimal
    horas_totais: Decimal
    # Rascunho não é atividade realizada e fica de fora. Contado para não sumir calado.
    rascunhos_no_mes: int
    # Dia 15 do mês seguinte, que é quando a entrega vence.
    prazo: date


class CroquiIn(BaseModel):
    """O arquivo exportado pelo aplicativo do drone.

    KML vai como texto. KMZ é zip, e por isso vai em base64, com ``base64=true`` — um
    campo explícito em vez de adivinhação, porque adivinhar erraria no arquivo que tiver
    o conteúdo parecido com o outro formato.
    """

    kml: str = Field(min_length=1)
    base64: bool = False
    origem: str | None = Field(default=None, max_length=200)


class CroquiOut(BaseModel):
    """O que foi lido do arquivo, e o que dele se deduz.

    A área e a direção são **sugestão**: o documento leva o que o agrônomo declarou.
    """

    faixas: int
    tem_limite: bool
    area_sugerida_ha: Decimal | None
    direcao_tiros_graus: Decimal | None
    latitude: Decimal | None
    longitude: Decimal | None


class AssinaturaIn(BaseModel):
    """A assinatura desenhada na tela.

    ``traco`` são as linhas do desenho: uma lista de linhas, cada uma uma lista de pontos
    ``[x, y]`` numa caixa de 0 a 1. Normalizado porque o mesmo traço feito num celular
    estreito e num tablet grande tem de imprimir igual.
    """

    papel: SignatureRole
    nome: str = Field(min_length=1, max_length=200)
    registro: str | None = Field(default=None, max_length=60)
    traco: list[list[list[float]]]


class AssinaturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    papel: SignatureRole
    nome: str
    registro: str | None
    assinado_em: datetime | None
    # Impressão digital do documento no momento da assinatura. Muda se o planejamento for
    # editado depois, e é assim que se descobre.
    documento_hash: str | None


class ConferenciaAssinaturasOut(BaseModel):
    """Quais assinaturas não correspondem mais ao documento.

    Vazio é o caso bom. Nome na lista significa que o planejamento mudou depois de
    assinado, e quem confere precisa saber disso antes do fiscal.
    """

    divergentes: list[SignatureRole]


class FlightLogPreviewIn(BaseModel):
    """O registro de voo exportado pelo aplicativo do drone, em base64.

    Base64 porque ``.xlsx`` é binário — é zip de XML. CSV vai pelo mesmo campo: quem
    descobre o formato é o conteúdo, não a extensão, que no caminho de um arquivo que
    atravessa celular, WhatsApp e computador quase sempre mente.
    """

    arquivo: str = Field(min_length=1, description="O .xlsx ou .csv dos voos, em base64.")
    #: Quanto somar ao horário do arquivo para chegar ao horário local, em minutos.
    #:
    #: O arquivo não declara fuso. A dedução — pelo horário do pôr do sol em Goiás — é que
    #: ele está em UTC, e por isso o padrão é -180 (três horas a menos). **É sugestão, e a
    #: resposta devolve os dois horários** para a tela oferecer o controle de alternar;
    #: converter calado erraria também a leitura de clima daquele horário.
    fuso_minutos: int = Field(default=-180, ge=-840, le=840)


class VooAuxiliarOut(BaseModel):
    """Voo que não pulverizou: translado, calibração, teste, decolagem abortada.

    **Não é descarte.** Ele desgasta motor, hélice e bateria igual, e é por isso que a
    revisão vence — entra no horímetro da aeronave e fica de fora do relatório do MAPA.
    """

    comecou_em: datetime
    terminou_em: datetime
    comecou_em_ajustado: datetime
    terminou_em_ajustado: datetime
    duracao_segundos: int
    aeronave: str
    equipamento_serie: str | None
    piloto: str | None
    lugar: str | None


class HorasDoEquipamentoOut(BaseModel):
    """O que cada equipamento voou no arquivo, para o horímetro e a manutenção."""

    equipamento_serie: str | None
    aeronave: str
    #: A aeronave cadastrada que tem este número de série, quando existe.
    aircraft_id: uuid.UUID | None
    prefixo: str | None
    voos: int
    duracao_total_segundos: int
    duracao_aplicando_segundos: int
    duracao_auxiliar_segundos: int


class AplicacaoDoVooOut(BaseModel):
    """Uma aplicação: os voos de um mesmo talhão, no mesmo dia, somados."""

    plot_id: str
    talhao: str | None
    dia: date
    #: Como está no arquivo, sem fuso.
    comecou_em: datetime
    terminou_em: datetime
    #: Com o deslocamento aplicado. É o que a tela mostra por padrão.
    comecou_em_ajustado: datetime
    terminou_em_ajustado: datetime
    area_ha: Decimal
    volume_l: Decimal
    volume_por_ha: Decimal | None
    #: Horas de execução, que o relatório mensal exige (Portaria 298/2021, art. 11, III).
    duracao_segundos: int
    voos: int
    aeronave: str
    #: O número de série do equipamento. É o que casa com a aeronave cadastrada — o nome
    #: que aparece no aplicativo é apelido, e apelido não identifica ARP para o MAPA.
    equipamento_serie: str | None
    #: A aeronave cadastrada, quando o série bate com alguma.
    aircraft_id: uuid.UUID | None
    prefixo: str | None
    piloto: str | None
    lugar: str | None
    largura_faixa_m: Decimal | None
    altura_voo_m: Decimal | None
    largura_faixa_min: Decimal | None
    largura_faixa_max: Decimal | None
    altura_voo_min: Decimal | None
    altura_voo_max: Decimal | None


class FlightLogPreviewOut(BaseModel):
    """O que o sistema entendeu do arquivo. **Nada foi gravado.**

    A leitura propõe e a pessoa confirma, como na entrada por nota do módulo `compras`
    (ADR 0009) e na importação do croqui. Em documento que vai ao MAPA, gravar sozinho o
    que um arquivo de terceiro disse é o caminho mais curto para um relatório divergente.
    """

    #: Como o arquivo mede área: "mu", "ha" ou "acre". Lida do cabeçalho, nunca suposta.
    unidade_de_area: str
    #: O deslocamento aplicado nos horários "ajustados", em minutos.
    fuso_minutos: int
    aplicacoes: list[AplicacaoDoVooOut]
    voos_auxiliares: list[VooAuxiliarOut]
    horimetro: list[HorasDoEquipamentoOut]
    #: Séries de equipamento que o arquivo traz e nenhuma aeronave cadastrada tem.
    #:
    #: A tela oferece o cadastro rápido com eles: sem a aeronave, o relatório mensal não
    #: tem o que pôr no campo de identificação da ARP (Portaria 298/2021, art. 11, II).
    series_sem_aeronave: list[str]
    avisos: list[str]


class VooConfirmadoIn(BaseModel):
    """Um voo como o operador o confirmou, depois de revisar.

    Os dois horários vêm: o escolhido, com fuso, e o do arquivo, sem fuso. O segundo é o
    que torna a reimportação reconhecível — o mesmo equipamento não decola duas vezes no
    mesmo segundo —, e é o dado bruto, que continua verdadeiro se amanhã se descobrir que
    o fuso do arquivo era outro.
    """

    #: Com deslocamento explícito. É o que vai para o documento.
    comecou_em: AwareDatetime
    terminou_em: AwareDatetime
    #: Sem fuso, exatamente como está no arquivo do equipamento.
    comecou_em_arquivo: datetime
    duracao_segundos: int = Field(ge=0, le=86_400)
    equipamento_serie: str | None = Field(default=None, max_length=60)
    equipamento_apelido: str | None = Field(default=None, max_length=120)
    piloto: str | None = Field(default=None, max_length=200)
    lugar: str | None = Field(default=None, max_length=400)
    #: Só nos voos auxiliares; nos da aplicação, vale a aeronave da aplicação.
    aircraft_id: uuid.UUID | None = None


class InsumoDaAplicacaoIn(BaseModel):
    """O defensivo que saiu do estoque nesta aplicação.

    A quantidade é a do produto, **não a de calda**: calda é mistura, e quase toda ela é
    água. A tela propõe a dose vezes a área executada, a partir do receituário, e quem confirma
    ajusta — deduzir produto a partir de litro de calda poria no estoque uma baixa que não
    aconteceu.
    """

    produto_id: uuid.UUID
    quantidade: Decimal = Field(gt=0)
    unidade_id: uuid.UUID | None = None
    lote_id: uuid.UUID | None = None


class AplicacaoConfirmadaIn(BaseModel):
    plot_id: str = Field(min_length=1, max_length=80)
    talhao: str | None = Field(default=None, max_length=200)
    aircraft_id: uuid.UUID | None = None
    #: O planejamento que esta aplicação executou, quando o operador casou os dois.
    plan_id: uuid.UUID | None = None
    area_ha: Decimal = Field(ge=0)
    volume_l: Decimal = Field(ge=0)
    largura_faixa_m: Decimal | None = Field(default=None, ge=0)
    altura_voo_m: Decimal | None = Field(default=None, ge=0)
    voos: list[VooConfirmadoIn] = Field(min_length=1)
    insumos: list[InsumoDaAplicacaoIn] = Field(default_factory=list)


class FlightLogConfirmIn(BaseModel):
    """O que o operador revisou e aprovou da importação.

    As duas listas vêm separadas porque significam coisas diferentes: aplicação vai ao
    relatório do MAPA, voo auxiliar vai ao horímetro da frota. Nenhuma das duas é
    descartada.
    """

    aplicacoes: list[AplicacaoConfirmadaIn] = Field(default_factory=list)
    voos_auxiliares: list[VooConfirmadoIn] = Field(default_factory=list)


class FlightLogConfirmOut(BaseModel):
    aplicacoes: int
    voos_gravados: int
    #: Já estavam registrados: reimportar o mesmo arquivo não duplica hora de voo.
    voos_repetidos: int
    baixas_de_estoque: int
    planos_atualizados: list[uuid.UUID]
    #: Inclui a divergência entre o que o planejamento dizia e o que o equipamento mediu.
    avisos: list[str]


class HorimetroOut(BaseModel):
    """As horas de uma aeronave, somadas do registro de voo importado.

    É consulta, e não contador guardado: contador precisaria ser corrigido a cada
    reimportação ou exclusão, e hora de voo errada é revisão vencida sem ninguém saber.
    """

    aircraft_id: uuid.UUID
    voos: int
    segundos_total: int
    segundos_aplicando: int
    segundos_auxiliar: int
    area_ha: Decimal
    primeiro_voo: datetime | None
    ultimo_voo: datetime | None
