# Auditoria arquitetural do Odoo 20.0

Referência congelada. Descreve como o Odoo resolve os mesmos problemas que o Decko enfrenta,
para servir de base de comparação — não de receita.

| | |
|---|---|
| Objeto auditado | `C:\Program Files\Odoo 20.0.20261021` (build `20261021`) |
| Data da auditoria | 21/10/2026 |
| Método | leitura estática do código instalado; o servidor **não** foi executado |
| Comparativo com o Decko | [`odoo-20-comparativo.md`](odoo-20-comparativo.md) |

Este documento não deve ser atualizado conforme o Decko evolui — ele é um retrato de uma versão
do Odoo. O que muda com o tempo é o comparativo.

---

## 1. Inventário

| Item | Valor |
|---|---|
| Versão | 20.0.0 final, LGPL-3 |
| Runtime | Python >= 3.12 e <= 3.14, PostgreSQL >= 16 |
| Núcleo (`server/odoo`, sem addons) | 205 arquivos `.py`, **76.524 linhas** |
| Addons Python | **1.301.836 linhas** |
| Addons JavaScript (sem `lib/`) | **1.199.863 linhas** |
| Arquivos XML | 6.316 |
| Módulos (`odoo/addons/*`) | **696** |
| Modelos declarados (`_name =`) | **1.633** |
| Dependências Python | ~60 pacotes, pinados às versões do Ubuntu 24.04 / Debian 12 |
| Opções de configuração | 106 (`tools/config.py`) |
| Tamanho em disco | 1,7 GB — `server/` 1,4 GB, interpretador embutido 282 MB |

A proporção entre núcleo e addons (76 mil contra 2,5 milhões de linhas) é a tese do Odoo:
framework pequeno, ecossistema grande.

**Observação relevante para o Decko:** o 20.0 passou a distribuir `server/skills/` — as diretrizes
oficiais de arquitetura em Markdown, versionadas junto ao código e escritas para agentes de IA
(`odoo-guidelines`, `odoo-web-guidelines`, `odoo-security`, `odoo-review`, `odoo-git`). É o mesmo
papel que `CLAUDE.md` e `docs/` cumprem aqui, com uma diferença de granularidade: uma seção por
regra, cada uma com o "por quê" e as exceções.

---

## 2. Camadas

```
┌──────────────────────────────────────────────────────────────┐
│ Cliente web — Owl 3 (plugins, signals), módulos AMD próprios │
├──────────────────────────────────────────────────────────────┤
│ Views declarativas: arch XML → view_compiler → template Owl  │
├──────────────────────────────────────────────────────────────┤
│ HTTP/WSGI (werkzeug): router + Dispatchers (http/jsonrpc/json2)│
├──────────────────────────────────────────────────────────────┤
│ ORM: Registry · Environment/Transaction · Field · Domain     │
├──────────────────────────────────────────────────────────────┤
│ Meta-modelo persistido: ir.model, ir.model.fields, ir.model.data│
├──────────────────────────────────────────────────────────────┤
│ sql_db: pool de conexões, Cursor, Savepoint                  │
├──────────────────────────────────────────────────────────────┤
│ PostgreSQL — um banco = um tenant = um registry              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. ORM

Reorganizado em `odoo/orm/` no 20.0. Os módulos públicos (`odoo/api`, `odoo/fields`,
`odoo/models`) viraram **fachadas de re-export**, e o comentário no código diz o motivo:
*"This is a `__init__.py` file to avoid merge conflicts on `odoo/api.py`"*. Engenharia de processo
virando arquitetura.

| Arquivo | Tamanho | Papel |
|---|---|---|
| `models.py` | 292 KB | `BaseModel`, CRUD, search/read_group, flush |
| `fields.py` + 9 `fields_*.py` | ~390 KB | descritores de campo |
| `domains.py` | 88 KB | AST de domínios |
| `registry.py` | 57 KB | registry por banco, caches, sinalização |
| `environments.py` | 59 KB | `Environment`, `Transaction`, `CacheLayer` |
| `model_classes.py` | 30 KB | construção dinâmica das classes de modelo |

### 3.1 Registry por banco

`Registry` é um `Mapping[str, type[BaseModel]]`. Instâncias ficam num LRU global de 42 bancos.
**Cada banco tem seu próprio conjunto de classes Python**, porque cada banco tem um conjunto
diferente de módulos instalados. É assim que "instalar um módulo para um cliente" funciona.

Caches nomeados, com tamanho e dependências de invalidação declaradas:

```python
_REGISTRY_CACHES = {'default': 8192, 'assets': 512, 'stable': 1024,
                    'templates': 1024, 'routing': 1024, 'groups': 64, ...}
_CACHES_BY_KEY  = {'groups': ('groups', 'default', 'templates', ...), ...}
```

### 3.2 Model definitions vs model classes

- **model definitions** — as classes escritas nos módulos. Estáticas.
- **model classes** — as do registry, **criadas dinamicamente**, herdando de todas as definitions
  daquele modelo em ordem reversa.

```
class A(Model): _name = 'a'        # A1          Model
class A(Model): _inherit = 'a'     # A2          / | \
class A(Model): _inherit = 'a'     # A3        A3 A2 A1
                                                \ | /
                                                  a      ← registry['a']
```

Três heranças, semânticas diferentes:

| Forma | Efeito | Tabela |
|---|---|---|
| `_name` | novo modelo | nova |
| `_inherit = 'x'` | **extensão horizontal**: campos e métodos entram no modelo existente | a mesma |
| `_inherits = {'x': 'x_id'}` | delegação: herda campos, **não** métodos | nova + FK |

`_inherit` é o que permite a um módulo de terceiros adicionar um campo em `res.partner` e vê-lo
aparecer no sistema inteiro, sem fork. É também a razão de o Odoo não ser tipável estaticamente.

### 3.3 Field como descritor

`class Field[T]` com `__set_name__`, `__get__`, `__set__`. Ler `record.name` consulta o cache do
`Environment`; em miss, dispara prefetch do campo **para todo o recordset**. É por isso que iterar
um recordset é barato e `browse(id)` em laço é caro.

Dois armazenamentos em `jsonb` na mesma coluna:

- `translate=True` → `{'en_US': ..., 'pt_BR': ...}`
- `company_dependent=True` → valor por empresa (substituiu `ir.property`)

### 3.4 Environment e Transaction

`Environment(cr, uid, context, su)` é **memoizado por transação**: `with_context(x=1)` repetido
devolve o mesmo objeto. `Transaction` guarda cache de registros, campos a recomputar e campos
protegidos.

O cache é um `CacheLayer` empilhável casado com savepoints: abrir savepoint empilha uma camada,
o rollback a descarta. Cache e banco não divergem. Recomputação por ponto fixo com teto
(`MAX_FIXPOINT_ITERATIONS = 10`).

### 3.5 Domain como AST

Antes: listas em notação polonesa. Agora: `DomainAnd`, `DomainOr`, `DomainNot`, `DomainBool`,
`DomainCondition`, `DomainCustom`, com `&`, `|`, `~` sobrecarregados e níveis de otimização.

```python
domain &= Domain("company_id", "in", companies)
```

Operadores reduzidos a um núcleo canônico (`any`/`not any`, `in`, comparações, família `like`);
`=`, `!=`, `child_of` são normalizados para ele. A notação antiga ainda é aceita na entrada.
Concatenar domínio do usuário sobre domínio de segurança é classificado como **injeção** pelo guia
de segurança.

### 3.6 Invalidação de cache entre processos

Tabelas `orm_signaling_registry`, `orm_signaling_default`, ... **insert-only**, onde cada worker lê
`max(id)`. O comentário explica a escolha:

```
# signaling was previously using sequence but this doesn't work with replication
# this is the reason why insert only tables are used.
```

Sequences não replicam logicamente; inserts replicam. O banco é o barramento, sem Redis.

### 3.7 Constraints e índices como atributos

```python
_check_qty = models.Constraint("CHECK (qty > 0)", "Quantidade deve ser positiva")
_name_uniq = models.UniqueIndex("(company_id, name)")
```

`_sql_constraints` (a API antiga) é **ignorado com warning** no 20: a constraint simplesmente não é
criada. Depreciação ruidosa no log e silenciosamente destrutiva no banco.

---

## 4. Meta-modelo persistido

`ir.model`, `ir.model.fields`, `ir.model.fields.selection`, `ir.model.constraint`,
`ir.model.relation`, `ir.model.inherit`, `ir.model.data`.

O schema é **derivado** das definições Python e espelhado em tabelas. Isso habilita quatro coisas:

1. **Campos e modelos customizados em runtime** (`x_*`), criados pela interface.
2. **XML ids** (`ir.model.data`): toda linha carregada por um módulo tem identidade estável
   `módulo.id`. Updates viram idempotentes e desinstalar um módulo é remover exatamente seus
   registros.
3. **Upgrades**: o framework compara schema declarado com existente e emite DDL.
4. **Introspecção para a UI**: `fields_get` alimenta as views.

O preço: o schema real não está em arquivo versionado. Não há migrations declarativas — há scripts
por módulo/versão (`MigrationManager`, fases `pre`/`post`/`end`) e, no 20, `odoo/upgrade_code/`:
**codemods que reescrevem o código dos addons entre versões** (`odoo-bin upgrade_code`). É a
resposta do Odoo a 20 anos de mudança de API com ecossistema de terceiros.

---

## 5. Camada HTTP

Pacote enxuto (~15 arquivos, nenhum acima de 26 KB).

- **Roteamento** gerado dos decoradores `@route`, com `routing_map` montada por chave de contexto
  (banco, idioma, website) e cacheada no registry.
- **Dispatchers plugáveis** — o melhor ponto de extensão do pacote:

  ```python
  class Dispatcher(ABC):
      def __init_subclass__(cls):
          _dispatchers[cls.routing_type] = cls
  ```

  Subclassificar **é** registrar. Hoje: `HttpDispatcher`, `JsonRPCDispatcher`, `Json2Dispatcher`,
  cada um com `pre_dispatch`, `dispatch`, `post_dispatch`, `handle_error`, `is_compatible_with`.
- **`auth`** por rota: `user`, `bearer` (exige `bearer_scope`), `public`, `none`.
- **CSRF** ligado por padrão em métodos não-seguros de rotas `type='http'`; rotas `jsonrpc`/`json2`
  são protegidas pelo content-type, por design.
- **`readonly`** por rota permite roteamento para réplica de leitura.
- **`retrying()`**: em `SerializationFailure`, rollback e nova tentativa — até 5 vezes, com backoff
  `random.uniform(0, 2**i)`. Concorrência otimista resolvida **na borda da requisição**, não
  espalhada pelo domínio. É consequência direta de usar isolamento REPEATABLE READ.

---

## 6. Runtime

| Classe | Uso |
|---|---|
| `ThreadedServer` | desenvolvimento e Windows |
| `PreforkServer` | produção POSIX: `WorkerHTTP` + `WorkerCron` |
| `GeventServer` | websocket / longpolling |

`Worker` recicla-se por `limit_request`, `limit_memory_soft/hard`, `limit_time_cpu/real`: trata
vazamento como política, não como conserto. Cron é um worker separado disputando advisory locks no
banco — não há broker de filas.

---

## 7. Sistema de módulos

- **`Manifest`** é um `Mapping` com 38 chaves default e só 3 obrigatórias (`name`, `author`,
  `license`). Notáveis: `depends`, `data`, `demo`, `assets`, `auto_install` (pode ser um
  *subconjunto* de `depends` que dispara a instalação), `external_dependencies` (`python`/`bin`),
  `pre_init_hook`/`post_init_hook`/`uninstall_hook`, `cloc_exclude`, `countries`.
- **`ModuleGraph`** ordena a carga em fases. `base` é sempre a fase 0 (*"base should always be the
  single drain of the dependency graph"*); dentro da fase a ordem é `(profundidade, nome)`, com
  profundidade = maior distância até `base`.
- **`load_modules`** usa advisory lock **compartilhado** para carregar e **exclusivo** para
  atualizar o registry: controle de concorrência entre workers feito no PostgreSQL.
- **Dados** carregados por `convert.py` (XML e CSV), com `noupdate` para o que o usuário pode
  editar, e `flush()` entre arquivos.

---

## 8. Segurança

### 8.1 `ir.access` — a mudança estrutural do 20.0

ACLs (`ir.model.access`) e record rules (`ir.rule`) foram **unificadas** em um modelo só, declarado
em `security/ir.access.csv`:

```csv
id,name,model_id,group_id/id,operation,domain
ir_attachment_public_rule,read public attachments,ir.attachment,base.group_user,r,"[('public','=',True)]"
```

- `operation` é subconjunto de `crud`. A linha vale só para as operações que lista.
- Linha **com grupo** = *permissão*, **OR**-eada sobre os grupos do usuário; o `domain` limita
  apenas o que aquela linha concede.
- Linha **sem grupo** = *restrição*, **AND**-eada sobre **todos** os usuários. Nunca concede nada,
  e restrições não-sobrepostas podem trancar todo mundo fora.
- **Default deny**: modelo sem linha de permissão é inacessível.
- Multiempresa exige restrição sem grupo: `[('company_id', 'in', company_ids)]`.

Todo o núcleo cabe em **142 linhas** de CSV.

Armadilha documentada: `write` checa só permissão de escrita, nunca de leitura — restrição que
cobre apenas `r` deixa alterar registros que a leitura esconde.

### 8.2 Modelo de ameaças

Do `skills/odoo-security/SKILL.md`, que é explícito ao ponto de listar os padrões a varrer:

- **Todo método público é endpoint RPC**, com argumentos escolhidos pelo atacante. Controle de
  acesso vale para CRUD, **não** para chamada de método. Daí: privado por padrão, `@api.private`
  para blindar nome público, `get_public_method` como guarda.
- **`sudo()` é o risco nº 1.** Sob `sudo()`, payloads `Command` de x2many executam com sudo **no
  comodelo**, salvo `_allow_sudo_commands = False`.
- **`related` é sudo-computado por padrão** (`related_sudo=True`): um `Many2one` gravável apontando
  para dado sensível vira leitura privilegiada arbitrária.
- **`safe_eval`** em domínios e server actions é superfície permanente — o próprio guia admite que
  "ainda dá capacidades amplas".
- Métodos que **retornam objetos ricos** são exploráveis de código `safe_eval`'d, caminhando por
  internals `_single_underscore`.
- XSS: `t-raw` deixou de existir nos dois QWeb; o vetor hoje é `Markup`/`markup()` chegando a
  `t-out`. f-string dentro de `Markup` derrota o escape.
- `consteq` para segredos, `file_open` (confinado aos addons paths) em vez de `open`, nunca
  `pickle`, nunca `getattr`/`setattr` em registro.

---

## 9. Cliente web

### 9.1 Owl 3 com sistema de plugins

```js
export const services = new Resource({ name: "services", validation: t.constructor(Plugin) });
const app = new App({ config: { env }, plugins: services, customDirectives, ... });
await app.pluginManager.ready;
```

**Services viraram Plugins do Owl.** Há um `owl2/owl3_compatibility_layer.js` para a transição.
`env` encolheu, e `makeEnv()` devolve um `Proxy` que **lança erro dizendo onde o valor foi parar**:

```js
const REMOVED_KEYS = { debug: `"env.debug" was removed when the debug mode became
  DebugModePlugin. Use usePlugin(DebugModePlugin) in a component ...` };
```

Depreciação que ensina em vez de devolver `undefined`.

### 9.2 Loader de módulos próprio

AMD caseiro de ~250 linhas. O que vale é o diagnóstico: `findErrors()` separa `cycle` (com o
caminho em texto), `failed`, `missing` e `unloaded`, e `reportErrors()` explica que `unloaded` é
**erro secundário** causado pelos anteriores. Em debug, injeta banner vermelho via `::before`.

### 9.3 Registries hierárquicos

`Registry extends EventBus`, com `subRegistries`, API encadeável, `KeyNotFoundError` /
`DuplicatedKeyError` e validação de schema **só em debug**. É o ponto de extensão genérico do
cliente: views, campos, widgets, comandos, ações e formatters são todos entradas de registry.

### 9.4 Assets em duas camadas

1. **Manifesto**: `'assets': {'web.assets_backend': [...]}`, com diretivas
   `('include', bundle)`, `('remove', glob)`, `('replace', ...)`, `('prepend', ...)` e globs.
2. **`ir.asset` em banco**: mesmas diretivas como dado, permitindo a um módulo, tema ou usuário
   alterar bundles sem tocar manifesto.

`ir_asset.py` resolve com **ordenação topológica dos addons** e uma estrutura `AssetPaths` que
levanta erro nomeando o bundle quando um path não existe. SCSS compilado no servidor (libsass),
com sourcemaps. `js_transpiler.py` (26 KB) converte módulos ES para o formato do loader.

### 9.5 Views

`ir.ui.view` guarda o `arch` XML, com herança por `inherit_id` + `position`/`xpath`.
`postprocess_and_fields` avalia `groups` e resolve campos; `get_views` tem cache com chave própria.
No cliente, `view_compiler.js` transforma o arch em **template Owl**.

Regra de ouro declarada: ancorar herança de view em **nome**, nunca em posição —
`//group[2]/field[3]` quebra no primeiro reorder do módulo pai.

### 9.6 Modelo relacional no cliente

`src/model/relational_model/` espelha o ORM no browser: `datapoint.js`, `record.js`,
`dynamic_record_list.js`, `static_list.js`, `group.js`. Mais `sample_server.js`, que gera dados
falsos plausíveis para views vazias.

### 9.7 Ações como dado

`ir.actions.act_window`, `act_url`, `server`, `client`, `report`, `todo`. A navegação do app é
registro no banco, não rota no código — é o que permite ao usuário criar menu sem programar, e o
que torna `ir.actions.server` (com `safe_eval`) um vetor.

---

## 10. Internacionalização

Export/import `.pot`/`.po`, mais leitores CSV/XML para dados. Valores traduzíveis em `jsonb` por
idioma, **termo a termo** para HTML/XML: `xml_translate`/`html_translate` percorrem a árvore e
traduzem só nós de texto, com `ParsedTranslation` reconciliando quando o fonte muda.

API atual: `self.env._("...", arg=...)` — só literais estáticos, interpolação por argumento
(placeholders nomeados permitem reordenar por idioma, e o framework valida e escapa). `_()` nu
infere o ambiente **inspecionando o frame do chamador**, e falha silenciosamente fora de métodos de
modelo. `.weblate.json` (134 KB) na raiz: tradução terceirizada ao Weblate.

---

## 11. Onde o Odoo acertou e onde doeu

### Acertou

1. **Registry por tenant + MRO em runtime** — extensibilidade real sem fork.
2. **Meta-modelo persistido com XML ids** — identidade estável é o que torna
   install/update/uninstall idempotentes.
3. **Domain como AST** — composição, otimização e proteção contra injeção de uma vez.
4. **Pontos de extensão formais** (`__init_subclass__`, registries) em vez de condicionais.
5. **Invalidação por tabela insert-only** — zero infraestrutura extra, sobrevive a replicação.
6. **`retrying()` na borda** — concorrência otimista em um lugar só.
7. **`CacheLayer` casada com savepoints** — cache e transação não divergem no rollback.
8. **Guidelines versionadas junto ao código.**
9. **Codemods de upgrade** — planejou a reescrita do código de terceiros.
10. **Depreciação que ensina** e **erro de build como feature** (causa primária separada da
    secundária).

### Doeu

1. **God objects.** `orm/models.py` com 292 KB; `translate.py` 120 KB; `misc.py` 71 KB. A
   reorganização para `odoo/orm/` no 20.0 é a confissão — e `models.py` seguiu monolítico.
2. **Monkeypatching no boot** (`odoo/_monkeypatches`, antes de tudo).
3. **`eval` de dados como primitiva de produto.** É o que torna o Odoo configurável *e* sua
   superfície de RCE estrutural.
4. **Herança de view por XPath** — frágil o bastante para merecer seção própria no guideline.
5. **Grafo sem fronteiras.** 696 módulos onde cada par de features que precisa se conhecer gera um
   módulo-ponte: `pos_self_order_bancontact_pay`, `mass_mailing_event_track_sms`.
6. **Schema sem migrations declarativas**, corrigido por scripts ad-hoc por versão.
7. **Sem fila de verdade** — cron fazendo polling com advisory lock.
8. **Escala por worker, não por serviço**: todo worker carrega os 696 módulos.
9. **`patch()` em JS** desencorajado pelo próprio guideline e ainda assim usado — sinal de ponto de
   extensão que faltou.
