# API do módulo Agro

Endpoints expostos pelo módulo `agro` hoje. Requisitos e origem dos campos estão em
`docs/discovery/agro-planejamento-operacional.md`; as decisões de implementação, em
`docs/adr/`.

Este documento existe para responder duas perguntas que o `/docs` gerado pelo FastAPI não
responde: **qual permissão cada endpoint exige** e **o que está declarado no manifesto mas
ainda não tem rota**.

## Base e autenticação

Todas as rotas vivem sob `/api/v1/agro` — o prefixo é montado pelo carregador de módulos a
partir do nome no `module.toml` (`apps/api/src/decko/modules.py`), não escrito no router.

Toda rota exige JWT de acesso e uma permissão nomeada. As permissões são declaradas em
`modules/agro/module.toml` e concedidas ao papel de administrador no `decko-admin bootstrap`.

O isolamento entre empresas **não** é feito por filtro na consulta: é Row Level Security no
PostgreSQL, aplicada ao papel `decko_app`. Um pedido autenticado só enxerga as linhas do
próprio tenant mesmo que o endpoint não filtre nada.

## Contratante — `agro.client.*`

| Método | Rota | Permissão |
|---|---|---|
| `GET` | `/clients` | `agro.client.read` |
| `POST` | `/clients` | `agro.client.write` |

`ClientIn`: `nome` (1–200), `cpf_cnpj` (11–14 dígitos, só números), `telefone?`, `email?`.
`ClientOut` acrescenta `id`.

## Propriedade — `agro.property.*`

| Método | Rota | Permissão |
|---|---|---|
| `GET` | `/properties` | `agro.property.read` |
| `POST` | `/properties` | `agro.property.write` |

`PropertyIn`: `client_id`, `nome`, `municipio`, `uf` (2 letras), `latitude?`, `longitude?`
em grau decimal.

## Aeronave — `agro.aircraft.*`

| Método | Rota | Permissão |
|---|---|---|
| `GET` | `/aircraft` | `agro.aircraft.read` |
| `POST` | `/aircraft` | `agro.aircraft.write` |

`AircraftIn`: `prefixo`, `modelo?`, `fabricante?`, `numero_serie?`. `AircraftOut`
acrescenta `id` e `is_active`.

`numero_serie` é o série do equipamento como o aplicativo do fabricante o escreve, e existe
para o registro de voo importado encontrar a aeronave — ver `POST /flight-log/preview`. É
único por empresa e opcional, porque aeronave cadastrada antes da importação não tem como
saber o número.

## Planejamento Operacional — `agro.plan.*`

| Método | Rota | Permissão |
|---|---|---|
| `GET` | `/plans` | `agro.plan.read` |
| `POST` | `/plans` | `agro.plan.write` |
| `POST` | `/plans/{plan_id}/weather` | `agro.plan.write` |
| `GET` | `/plans/{plan_id}/weather` | `agro.plan.read` |
| `GET` | `/plans/{plan_id}/pdf` | `agro.plan.export` |

`POST /plans` responde **201** quando o planejamento nasceu agora e **200** quando
reconheceu um reenvio. O reenvio existe porque o planejamento é preenchido na lavoura, sem
sinal: `PlanIn` aceita um `id` escolhido pelo aparelho, e mandar o mesmo pacote duas vezes
devolve o que já está aqui em vez de gastar outro número de documento. Quem está online
não manda `id` — o servidor gera, como sempre fez. Ver a fatia 6 da
`docs/adr/0022-offline-first-as-respostas.md`.

`PlanIn` aceita a identidade opcional (`id`), os vínculos (`client_id`, `property_id`,
`aircraft_id?`), os dados da aplicação (`data_aplicacao?`, `cultura?`, `cultura_outras_texto?`, `tipos_aplicacao?`,
`area_ha?`, `latitude?`, `longitude?`) e os parâmetros que definem a janela de aplicação:

- `param_temperatura_maxima_c`
- `param_umidade_relativa_min_pct`
- `param_velocidade_vento_max_kmh`
- `param_largura_faixa_m`
- `param_altura_voo_m`

Os três primeiros são o que a captura meteorológica confronta. `numero` e `status` são
atribuídos pelo sistema.

### Captura meteorológica

`POST /plans/{plan_id}/weather` — `WeatherCaptureIn`: `data`, `periodo`, `momento`, `hora`,
`latitude?`, `longitude?`. Sem coordenada no corpo, vale a do planejamento.

A resposta (`201`) traz `leitura` e `alertas`. `alertas` é a lista de **quais** limites
foram rompidos, em texto; `leitura.violou_parametro` é o booleano equivalente. A leitura
guarda `source` (`api`, `manual`, `sensor`), `provider`, `captured_at` e o payload íntegro
do provedor — é o que a torna defensável em disputa de deriva (ver ADR 0003).

Respostas de erro:

| Código | Quando |
|---|---|
| `404` | planejamento inexistente |
| `422` | pedido recusado pela regra do domínio (`service.PlanError`) |
| `502` | o provedor externo falhou — a culpa não é de quem chamou |

### Exportação

`GET /plans/{plan_id}/pdf` devolve `application/pdf` com
`Content-Disposition: attachment; filename="planejamento-operacional-{numero}.pdf"`.
Estrutura e motivos em `docs/adr/0016-geracao-do-pdf.md`.

## Registro de voo do drone — `POST /flight-log/preview`

| Método | Rota | Permissão |
|---|---|---|
| `POST` | `/flight-log/preview` | `agro.plan.write` |

Lê o registro de voo exportado pelo DJI SmartFarm — **`.xlsx` ou `.csv`** — e devolve o que
ele descreve, para revisão. `FlightLogPreviewIn`:

- `arquivo`: o conteúdo em base64. Quem descobre o formato é o conteúdo, não a extensão.
- `fuso_minutos`: quanto somar ao horário do arquivo para chegar ao horário local. Padrão
  `-180`.

**Esta rota não grava nada.** Ela propõe; confirmar é outro passo. O motivo está no destino
do dado: o relatório mensal é obrigatório, vai ao SIPEAGRO até o dia 15 do mês seguinte, e a
sanção por irregularidade é multa, suspensão ou cancelamento do registro. Gravar sozinho o
que um arquivo de terceiro disse é o caminho mais curto para um relatório divergente.

O que ela resolve, e as armadilhas do arquivo, estão na seção 7.5 do
`docs/discovery/agro-planejamento-operacional.md`:

- **A área vem em `mu`** (1/15 de hectare) quando a conta do aplicativo está assim
  configurada, e a unidade só aparece no cabeçalho da coluna de consumo. `unidade_de_area`
  diz qual foi lida. Cabeçalho que o leitor não reconhece devolve **422** em vez de
  converter por palpite.
- **Um voo não é uma aplicação.** Os voos do mesmo `Plot ID` no mesmo dia são somados numa
  `AplicacaoDoVooOut`: área em hectare, volume de calda, dose por hectare, duração somada
  (as *horas de execução* do art. 11, III) e o início do primeiro voo com o fim do último.
- **O horário vem dos dois jeitos.** `comecou_em` é o do arquivo, que não declara fuso;
  `comecou_em_ajustado` tem o deslocamento aplicado. A tela oferece o controle de alternar,
  porque errar o fuso desloca o horário declarado **e** a leitura de clima que o confronta.
- **Voo que não pulverizou não é descartado.** Translado, calibração, teste e decolagem
  abortada vão em `voos_auxiliares` e entram no `horimetro` — eles desgastam motor, hélice e
  bateria igual, e é por isso que a revisão vence. Só a aplicação vai ao relatório do MAPA.
- **A aeronave é encontrada pelo número de série** (`Aircraft.numero_serie`), não pelo
  apelido que aparece no aplicativo: apelido não identifica ARP. `aircraft_id` e `prefixo`
  vêm preenchidos quando o série bate; `series_sem_aeronave` lista o que não bateu, para a
  tela oferecer o cadastro rápido.

`horimetro` traz, por equipamento: `voos`, `duracao_total_segundos`,
`duracao_aplicando_segundos` e `duracao_auxiliar_segundos`.

`avisos` traz o que quem confirma precisa saber antes de confirmar — unidade convertida,
ausência de fuso nos horários, voos sem aplicação, aeronave trocada no meio da aplicação.

Respostas de erro:

| Código | Quando |
|---|---|
| `422` | o arquivo não é um registro de voo legível, ou a unidade da área é desconhecida |

### Ainda sem rota: `POST /flight-log/confirm`

Gravar o que foi revisado — criar as aplicações, vincular o receituário, somar as horas na
aeronave e, quando houver, dar baixa nos insumos — **não existe ainda**, e depende de duas
coisas que não são código: a regra de divergência entre a área planejada e a aplicada
(pergunta 2 da seção 7.6 do discovery) e `comercial` entrar no `depends` do módulo, porque
baixa de estoque é serviço dele — ver `docs/adr/0007-dependencia-entre-modulos.md`.

## Conjuntos fechados

Os valores vêm do talão em uso. Acrescentar um exige migração, de propósito — ver
`modules/agro/src/decko_modules/agro/enums.py`.

| Enum | Valores |
|---|---|
| `Cultura` | `pastagens`, `cana_de_acucar`, `cafe`, `milho`, `citrus`, `eucalipto`, `soja`, `outras` |
| `TipoAplicacao` | `maturador`, `herbicida`, `fungicida`, `inseticida`, `adubacao`, `outros` |
| `EquipamentoTipo` | `barras_bicos`, `eletrostatico`, `solidos`, `atomizadores`, `outros` |
| `PlanStatus` | `rascunho`, `concluido`, `assinado`, `enviado` |
| `Periodo` | `matutino`, `vespertino` |
| `Momento` | `inicio`, `final` |
| `WeatherSource` | `api`, `manual`, `sensor` |
| `SignatureRole` | `eng_agronomo`, `piloto_agricola`, `tec_agricola_executor`, `proprietario_preposto` |
| `MaintenanceMoment` | `inicial`, `final` |

## Declarado no manifesto, ainda sem rota

O `module.toml` declara catorze permissões; nove têm endpoint. As cinco restantes existem
porque o modelo de dados já as prevê, e ficam registradas aqui para que a diferença entre
manifesto e API seja visível em vez de surpresa:

| Permissão | Falta |
|---|---|
| `agro.product.read` / `agro.product.write` | cadastro de produto — hoje o produto entra como texto no planejamento |
| `agro.prescription.read` / `agro.prescription.write` | receituário agronômico, com o CREA do responsável |
| `agro.plan.sign` | as quatro assinaturas; no PDF ainda são campo em branco para caneta (ver Q5 do discovery) |

Acompanhe em `docs/ROADMAP.md`, Fase 2.
