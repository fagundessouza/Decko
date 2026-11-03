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

`AircraftIn`: `prefixo`, `modelo?`, `fabricante?`. `AircraftOut` acrescenta `id` e
`is_active`.

## Planejamento Operacional — `agro.plan.*`

| Método | Rota | Permissão |
|---|---|---|
| `GET` | `/plans` | `agro.plan.read` |
| `POST` | `/plans` | `agro.plan.write` |
| `POST` | `/plans/{plan_id}/weather` | `agro.plan.write` |
| `GET` | `/plans/{plan_id}/weather` | `agro.plan.read` |
| `GET` | `/plans/{plan_id}/pdf` | `agro.plan.export` |

`PlanIn` aceita os vínculos (`client_id`, `property_id`, `aircraft_id?`), os dados da
aplicação (`data_aplicacao?`, `cultura?`, `cultura_outras_texto?`, `tipos_aplicacao?`,
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
Estrutura e motivos em `docs/adr/0004-geracao-do-pdf.md`.

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
