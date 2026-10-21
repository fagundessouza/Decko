# Decko × Odoo 20 — comparativo

Documento **vivo**. Mede as decisões do Decko contra as do Odoo, dimensão por dimensão, e separa
três coisas que é fácil confundir:

- **Divergência deliberada** — o Odoo faz diferente e o Decko tem motivo registrado. Não é dívida.
- **Lacuna** — o Odoo resolve um problema que o Decko ainda vai ter e hoje não resolve.
- **A avaliar** — depende de requisito que ainda não existe. Não antecipar (`CLAUDE.md`).

Referência congelada do lado Odoo: [`odoo-20-arquitetura.md`](odoo-20-arquitetura.md).

**Como usar:** antes de propor arquitetura, veja se a dimensão já está decidida aqui. Ao fechar uma
lacuna, registre o ADR e atualize a linha. Ao concluir etapa do roadmap que mexa numa dimensão,
revise a linha correspondente.

Última revisão: 21/10/2026 — estado do Decko: Fase 1 concluída, Fase 2 quase completa, ativação de
módulo por empresa implementada (lacuna 4.1 fechada).

---

## 1. Linha de base quantitativa

Para medir crescimento, não para comparar tamanho: o Odoo é um ERP completo com 20 anos.

| Métrica | Odoo 20 | Decko (21/10/2026) |
|---|---|---|
| Linhas de Python de aplicação | 76.524 (núcleo) + 1.301.836 (addons) | 4.184 |
| Linhas de teste | — (misturadas nos addons) | 2.293 |
| Linhas de frontend | 1.199.863 | 2.974 |
| Módulos | 696 | 2 implementados (`core`, `agro`) + 1 reservado |
| Modelos / entidades | 1.633 | 17 classes mapeadas |
| Migrações | scripts ad-hoc por versão | 3 (Alembic, ramificadas por módulo) |
| Permissões declaradas | grupos + 142 linhas de `ir.access` no núcleo | 23 strings de permissão |
| Funções de teste | — | 107 |
| Opções de configuração | 106 | — |

O número que importa vigiar é a **razão entre linhas de núcleo e linhas de módulo**. No Odoo é
1:17. Se no Decko o `apps/api` crescer mais rápido que `modules/`, a modularidade está vazando
para o host.

---

## 2. Dimensões decididas

| Dimensão | Odoo 20 | Decko | Veredito |
|---|---|---|---|
| **Isolamento entre clientes** | 1 banco = 1 tenant = 1 registry | 1 banco, RLS por `tenant_id` via GUC `decko.tenant_id` com `SET LOCAL` | **Divergência deliberada.** Mais barato de operar e nega por padrão. Custo: customização de schema por tenant deixa de ser trivial. ADR 0002 trata do papel sem `BYPASSRLS` |
| **Filtro de consulta** | `Domain` como AST interpretado | SQLAlchemy + Pydantic, tipado estaticamente | **Divergência deliberada.** Erro de filtro vira erro de tipo, não de runtime. Volta a ser problema se a interface precisar de filtro salvo pelo usuário (ver §4) |
| **Superfície RPC** | todo método público é endpoint; acesso checado só no CRUD | rotas FastAPI explícitas | **Divergência deliberada e melhor.** Nada é exposto por acidente |
| **Expressão dinâmica em dado** | `safe_eval` em domínios e server actions | não existe | **Divergência deliberada e melhor.** Manter assim: é a superfície de RCE estrutural do Odoo |
| **Invalidação de cache multi-worker** | tabelas `orm_signaling_*` insert-only | Redis (previsto na arquitetura) | **Divergência justificada.** O truque do Odoo serve a quem não quer dependência extra; o Redis já está na stack |
| **Assets do frontend** | bundles declarativos em duas camadas + ordenação topológica + libsass | Vite com code splitting por módulo | **Divergência deliberada.** O bundler moderno resolve o que o Odoo teve de construir |
| **Telas** | `arch` XML em banco, herança por XPath | React, telas em código | **Divergência deliberada.** Perde: usuário customizar tela sem programar. O próprio Odoo tem seção de guideline só para a fragilidade do XPath |
| **Grafo de módulos** | fases + profundidade, `base` como sorvedouro único | `resolve_order`: DFS topológico com detecção de ciclo e de dependência ausente | **Equivalente, mais simples.** Suficiente enquanto não houver carga em fases |
| **Manifesto** | 38 chaves com default, 3 obrigatórias | `module.toml`: identificação, `depends`, `required`, `branch_label`, `permissions`, `menu` | **Decko mais enxuto.** Adequado ao tamanho atual |
| **Versionamento de schema** | derivado dos campos + scripts por versão | Alembic, ramificado por módulo (`branch_label`) | **Decko melhor.** É a lacuna nº 6 do Odoo resolvida desde o início |
| **Fila de trabalho** | cron worker com polling e advisory lock | Redis + `apps/worker` (previsto) | **Decko melhor**, quando `apps/worker` existir |
| **Processo** | monólito; todo worker carrega os 696 módulos | monólito modular; `apps/api` carrega todos os módulos descobertos | **Mesma escolha, mesmo limite.** O processo carrega tudo; o que a empresa alcança é decidido na ativação |
| **Entrada por ramo de negócio** | sem conceito próprio: o cliente instala "apps" avulsos, e o agrupamento por indústria vive fora do código aberto | `profiles/*.toml`: conjunto nomeado de módulos, conferido contra os manifestos na inicialização; um clique contrata o conjunto | **Decko melhor no que já existe.** Falta a metade pesada: o Odoo acopla dado-semente ao módulo, e isso depende da lacuna 4.3. ADR 0005 |
| **Ativação de módulo por cliente** | implícita no registry: módulo não instalado não existe naquele banco | `tenant_module` + verificação aplicada pelo host na montagem do router; porta invertida para o host não importar módulo | **Divergência obrigatória.** Banco único exige mecanismo próprio. ADR 0004. Ganho sobre o Odoo: a proteção vem da montagem, então um módulo não consegue ficar aberto por omissão |
| **Diretrizes para quem mantém** | `skills/`, uma seção por regra, com o porquê | `CLAUDE.md` + `docs/` | **Equivalente.** O Odoo é mais granular: regra por seção, com exceções explícitas |

---

## 3. Onde o Odoo não serve de referência

Registrado para ninguém procurar resposta onde ela não existe:

- **Offline-first.** `docs/ARCHITECTURE.md` §8 trata escrita local com sincronização e resolução de
  conflito como decisão estrutural. O Odoo não tem isso: o cliente web assume servidor acessível, e
  o PDV offline é caso especial, não propriedade do framework. Aqui o Decko está à frente por
  requisito, e vai ter de inventar.
- **Leveza.** 1,7 GB em disco, interpretador embutido de 282 MB, todo worker carregando 696
  módulos. O alvo do Decko (PC antigo de caixa, celular fraco) é incompatível com esse perfil.
- **Mobile.** Capacitor/Tauri não têm equivalente no Odoo.
- **IA local.** Não existe no Odoo 20.

---

## 4. Lacunas que exigem decisão

Em ordem de urgência. Nenhuma foi promovida ao `ROADMAP.md` — isso é decisão de escopo do dono do
projeto, não deste documento.

### 4.1 Ativação de módulo por tenant — **fechada em 21/10/2026**

Resolvida por `docs/adr/0004-ativacao-de-modulo-por-empresa.md`. Promovida para a §2.

Como ficou: tabela `tenant_module` no núcleo, com RLS; o host aplica a verificação ao montar o
router de cada módulo não obrigatório, de modo que a proteção não depende de o módulo lembrar de
se proteger; e o host chega à verificação por uma porta que o núcleo preenche, sem importar módulo.

Fica registrado o que **não** foi feito: perfil de segmento ("supermercado", "distribuidora") é um
conjunto nomeado de módulos e continua inexistente — é camada fina sobre esta, e não faz sentido
nomear conjuntos antes de haver módulos para agrupar.

### 4.2 Extensão de entidade entre módulos — sem mecanismo

`docs/ARCHITECTURE.md` §2 diz: *"um módulo nunca importa diretamente de outro módulo irmão"*. A
regra é boa e é exatamente o que evita o emaranhado de 696 módulos do Odoo. Mas ela deixa uma
pergunta sem resposta: **como o módulo `distribuidora` adiciona um campo em `core.tenant`?**

No Odoo é `_inherit` e acaba. No Decko, hoje, não há caminho — e esse requisito aparece na primeira
vez que um segundo vertical precisar de um dado no cadastro da empresa.

Caminhos: tabela de extensão 1:1 por módulo (`core_tenant_distribuidora`); coluna JSONB de extensão
com schema declarado no manifesto; ou aceitar que só o `core` evolui o `core` e módulos pedem
campo por PR. O terceiro é honesto e barato enquanto o projeto tiver um desenvolvedor.

**Precisa de ADR** antes da Fase 5.

### 4.3 Identidade estável para dados de módulo — **virou bloqueio em 21/10/2026**

Deixou de ser dívida distante: é o que sustenta o "um clique e o ambiente fica pronto".

Auditoria do mecanismo no Odoo 20 (`addons/pos_restaurant`):

- A vertical é **fina**. `pos_restaurant` declara `'depends': ['point_of_sale']` — uma única
  dependência. O que o módulo traz de próprio são dois ou três modelos (salão, comanda) e, acima
  de tudo, **dado-semente**: `data/scenarios/restaurant_preset.xml`, categorias de bar e de
  restaurante, plantas de salão.
- Cada registro-semente tem **identidade externa estável**: `<record id="pos_takeout_preset">`
  resolve por `ir.model.data` para uma linha concreta. É isso que torna a carga repetível.
- Os blocos vêm com `noupdate="1"`: atualizar o módulo **não** sobrescreve o que o cliente já
  ajustou. Semente é ponto de partida, não configuração imposta para sempre.

A consequência para o Decko é direta: sem equivalente de `ir.model.data`, "ativar o perfil
supermercado" não tem como ser idempotente (reativar duplica), nem reversível (desativar não sabe
o que remover), nem seguro em atualização (sobrescreveria ajuste do cliente).

O caminho continua o mesmo descrito abaixo, e agora tem prazo.



Não há equivalente de `ir.model.data`. Hoje os dados-semente (papéis, permissões) vêm do bootstrap
e das migrations. Consequências: desinstalar um módulo não tem como remover exatamente os dados que
ele criou, e reinstalar pode duplicar.

Ainda não dói, porque nenhum módulo tem catálogo-semente. Vai doer na Fase 5 (distribuidora traz
unidades, categorias, tabelas de preço).

Caminho: tabela `module_data` mapeando `(module, external_id) → (table, pk)`, escrita pelo
carregador de dados. É o `ir.model.data` do Odoo em versão mínima, e vale copiar o conceito.

### 4.4 Nível de isolamento de transação — nunca declarado

`db.py` cria o engine sem definir `isolation_level`, então vale o padrão do PostgreSQL:
**READ COMMITTED**. Isso nunca foi uma decisão; é um default herdado.

Importa em dois pontos que já existem: a consolidação mensal (`consolidation.py`) lê muitas linhas
e pode compor um fechamento a partir de estados diferentes do banco; e qualquer numeração sequencial
de documento está sujeita a corrida.

Caminhos: declarar READ COMMITTED explicitamente e proteger os pontos críticos com
`SELECT ... FOR UPDATE`; ou subir para REPEATABLE READ e então **copiar o `retrying()` do Odoo**,
que é a peça que falta para isso ser viável (rollback + nova tentativa com backoff, na borda da
requisição, até 5 vezes).

**Precisa de ADR** — muda o contrato de concorrência de todo o sistema.

### 4.5 Regras de registro além do tenant

A RLS cobre a fronteira entre empresas. As permissões são strings planas no manifesto. Não há como
expressar *"este usuário vê apenas os planejamentos da sua própria filial"*.

O Odoo resolve com o `domain` das linhas de `ir.access`, e o modelo dele vale estudar quando a hora
chegar: linha com grupo concede (OR), linha sem grupo restringe (AND), default deny — unificado num
único lugar, o que no Odoo só aconteceu na versão 20 depois de anos com dois sistemas separados.

**A avaliar.** Não antecipar: nenhum requisito atual pede. Mas se pedir, começar unificado.

### 4.6 Internacionalização

Hoje pt-BR fixo, sem maquinário. Coerente com o domínio (regulação brasileira).

Registrado só pelo custo de retrofit: o Odoo guarda valor traduzível em `jsonb` por idioma e
traduz HTML **termo a termo**. Retrofitar isso depois de ter dezenas de tabelas é caro. Se o
mercado internacional entrar no escopo do produto (e não só do portfólio), é decisão de schema, não
de interface.

### 4.7 Atualização de módulo de terceiros

Não aplicável hoje — não há terceiros. Anotado porque é a dívida que o Odoo pagou por 20 anos e
cuja solução (`upgrade_code`, codemods que reescrevem o código dos addons) só chegou no 20.0.

Se o Open Core atrair módulos de fora, a pergunta "como eu quebro a API sem quebrar todos eles"
precisa de resposta antes do primeiro módulo de terceiro, não depois.

---

## 5. Padrões do Odoo que valem adotar sem mudar de arquitetura

Independentes de ORM, aplicáveis como estão:

1. **`retrying()` na borda da requisição** — se 4.4 subir o isolamento. `odoo/http/retrying.py`.
2. **`module_data`** como `ir.model.data` mínimo — fecha 4.3.
3. **Depreciação que ensina.** O `Proxy` de `makeEnv()` lança erro dizendo onde a chave foi parar,
   em vez de devolver `undefined`. Barato, e transforma a manutenção.
4. **Erro de carga com causa primária separada da secundária.** O loader do Odoo distingue
   `cycle`, `failed`, `missing` e `unloaded`, e diz que o último é consequência dos outros.
   `modules.py` já erra bem em ciclo e dependência ausente; vale manter esse padrão ao crescer.
5. **Granularidade das diretrizes.** Uma seção por regra, com "por quê" e "exceções", como
   `skills/odoo-guidelines/guidelines/*.md`. O `CLAUDE.md` já tem as regras; o que falta é o porquê
   em cada uma — e é o porquê que impede a regra de ser contornada por engano.
6. **Varredura de segurança por padrão.** `skills/odoo-security/SKILL.md` lista o que procurar e o
   que faz de cada achado um problema. O equivalente aqui seria uma lista curta: `sudo`/escalonamento
   de papel, SQL cru, `eval`, `open()`, comparação de segredo com `==`, rota sem verificação de
   permissão, campo sensível em resposta de API.

---

## 6. Manutenção deste documento

- A auditoria (`odoo-20-arquitetura.md`) é **congelada**. Se um dia for auditada outra versão do
  Odoo, crie `odoo-NN-arquitetura.md` ao lado; não edite a antiga.
- Este comparativo é **vivo**: toda lacuna fechada vira ADR + linha atualizada na §2, e sai da §4.
- A linha de base da §1 deve ser remedida a cada fase concluída. O que se observa não é o tamanho,
  é a razão núcleo/módulos.
