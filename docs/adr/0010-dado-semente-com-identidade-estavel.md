# ADR 0010 — Dado-semente com identidade estável

- **Data:** 2026-10-28
- **Status:** aceito
- **Depende de:** ADR 0004 (ativação de módulo por empresa), ADR 0005 (perfil de segmento),
  ADR 0007 (dependência entre módulos)
- **Fecha:** lacuna 4.3 de `docs/benchmark/odoo-20-comparativo.md`

## Contexto

A ADR 0005 implementou metade do perfil de segmento — o conjunto nomeado de módulos — e
adiou a outra metade com uma condição escrita: *"até existir módulo que tenha semente para
carregar"*. Essa condição venceu. O módulo `comercial` existe, com unidade e categoria em
árvore, e `compras` e `pdv` se apoiam nele.

O que falta aparece na primeira tela. Uma empresa nova que contrata "Comércio em geral"
recebe os módulos certos e cai numa tela de unidades vazia, onde precisa inventar a árvore
de medidas antes de cadastrar o primeiro produto. O "um clique" de hoje **instala**; ele
não **configura**. É a diferença que a ADR 0005 pediu para não se perder, e é ela que este
documento fecha.

### O que a auditoria do Odoo mostra, e o que ela ensina a não copiar

O mecanismo é `ir.model.data`: cada registro-semente tem um identificador externo
`modulo.nome` que resolve para uma linha concreta (modelo + id). É isso que torna a carga
repetível. Dois detalhes do comportamento importam aqui, e eles não são os que a leitura
superficial sugere:

- `noupdate="1"` protege o registro na **atualização** do módulo. É uma declaração do autor
  do módulo, feita antes de existir cliente: ele precisa adivinhar o que o cliente vai
  querer ajustar.
- A **desinstalação** é outra história: ela apaga aquilo que as linhas de `ir.model.data`
  daquele módulo apontam, independentemente de `noupdate`. Registro sem identificador
  externo próprio sobrevive; registro com identificador vai embora.

Ou seja: no Odoo, "eu semeei esta linha" e "esta linha é minha e eu a apago quando sair"
são a mesma informação. Para o Decko isso é um defeito, não um modelo — a categoria que o
lojista usou em trezentos produtos não pode depender de o módulo ter sido desinstalado.

## Decisão

### 1. A identidade mora em tabela própria do núcleo: `seed_record`

| Coluna | Para quê |
|---|---|
| `tenant_id` | A semente é **por empresa**. Cada uma recebe a sua cópia de "Unidade" |
| `module_name` | Quem semeou |
| `ref` | Identificador estável, escrito pelo módulo: `comercial.unidade.un` |
| `table_name` + `row_id` | Para onde o `ref` resolve |
| `fingerprint` | SHA-256 dos campos que a semente escreveu — ver decisão 5 |
| `status` | `ativo` ou `removido` — ver decisão 4 |

Única em `(tenant_id, module_name, ref)`, com RLS como toda tabela do projeto. É tabela de
plataforma, então nasce no núcleo e na ramificação de migração dele.

`table_name` + `row_id` não tem chave estrangeira: o destino é dinâmico, e não há como
apontar para uma tabela escolhida em tempo de execução. A consequência é assumida — a
linha de registro pode sobreviver ao desaparecimento do destino, e por isso o carregador
trata ausência como caso normal, não como erro.

### 2. A semente é do módulo que possui a tabela, e entra pelo serviço dele

Uma **terceira porta invertida**, no mesmo padrão da ADR 0004: o host declara
`SeedLoader`, cada módulo registra o seu na importação, e o host aplica sem conhecer
schema nenhum. O host sabe apenas *"módulo X, conjunto de semente S, empresa T"*.

Duas razões, e a segunda é a que não é negociável:

- A ADR 0007 proíbe módulo escrever na tabela de outro. Semente é escrita. Sem a porta, o
  perfil `comercio` escreveria em `comercial_unidade`.
- O serviço calcula o que a tabela não guarda sozinha. `criar_unidade` resolve `fator` e
  `raiz_id` subindo a árvore; semente que faça `INSERT` direto produz uma árvore que
  **parece** certa e converte errado. Passar pelo serviço não é elegância, é correção.

O formato do arquivo de semente dentro do módulo é assunto do módulo. O host não o lê.

### 3. A semente entra na ativação, e só nela

Diferente das permissões, que a ADR 0004 passou a reconciliar na subida da aplicação.
A assimetria é deliberada:

- Permissão **tem** de alcançar quem já usa o módulo. Sem isso, a versão nova abre uma
  tela em "permissão necessária". Foi o defeito que `agro.pilot.read` expôs.
- Semente é **dado do cliente** a partir do instante em que entra. Acrescentar uma
  categoria ao catálogo de quem já opera, um ano depois, numa subida de aplicação que
  ninguém pediu, é intrusão.

Conjunto de semente novo numa versão nova alcança empresa existente **só quando ela pede**.

E ela pede pela vitrine: `POST /core/modules/{nome}/seed`, com o botão "Trazer itens iniciais"
no cartão do módulo instalado. O catálogo diz quais módulos têm o que trazer (`has_seed`),
respondido pelo host a partir do que foi registrado — e não por uma lista escrita à mão na
interface, que sairia de sincronia no primeiro módulo novo. Exige `core.module.activate`:
é a mesma permissão de contratar módulo, porque é a mesma classe de ato. Semear módulo não
contratado é recusado — criaria catálogo para tela que nem abre.

### 4. Idempotência pelo registro, nunca por busca por nome

Reativar um módulo consulta `seed_record`, não o catálogo:

- `ref` registrado e linha de destino existindo → não faz nada.
- `ref` registrado e linha de destino apagada pelo cliente → **não recria**, e marca
  `status = removido`.

O segundo caso é o que justifica a decisão. Ressuscitar o que alguém apagou de propósito é
a falha pior, porque ela reaparece sem explicação e o cliente não tem como impedir.

### 5. A atualização olha o dado, não um aviso do autor

`fingerprint` guarda o hash dos campos que a semente escreveu. Na hora de atualizar:

- Linha ainda bate com o hash → ninguém mexeu, a versão nova pode corrigir.
- Linha divergiu → o cliente ajustou, e o ajuste dele vale mais que a semente.

**O que entrou nesta implementação:** o `fingerprint` e a função que responde "o cliente
mexeu nisto?" (`core.seed.intacta`). O **atualizador** não entrou, e de propósito: não
existe ainda versão de módulo que precise corrigir semente já entregue, e construir o
caminho antes do primeiro caso seria a abstração sem consumidor que o `CLAUDE.md` veda. O
que precisava existir desde já é o **registro** do que foi escrito — sem ele, o primeiro
módulo que precisar atualizar não terá como saber o que era seu.

É a divergência deliberada em relação ao `noupdate` do Odoo. Lá o autor do módulo declara
antes se o cliente vai querer editar; aqui o sistema simplesmente **confere**. Guarda-se o
hash e não os valores, por duas razões: a regra 2 do `CLAUDE.md` (não espalhar dado do
cliente por tabela de infraestrutura) e o tamanho da tabela.

### 6. Desativar não remove semente

A ADR 0004 já decidiu que desativar módulo preserva os dados. Semente segue a regra, e
dois fatos a reforçam: a chave estrangeira de `comercial_unidade.referencia_id` e de
`comercial_categoria.pai_id` é `RESTRICT`, então linha em uso não é apagável de qualquer
modo; e o que o cliente quer de verdade não é "desinstalar e limpar", é **"tirar os
exemplos que eu não usei"**.

É isso que o registro passa a permitir, como ação explícita de quem opera: as linhas com
`ref` registrado, intactas pelo `fingerprint` e sem referência apontando para elas. A ação
não entra nesta decisão — entra o que a torna possível.

### 7. Linha que o cliente já criou à mão não é reivindicada

Apareceu na implementação, e vale como decisão. `comercial_unidade` tem nome único por
empresa, então semear "Unidade" numa empresa que já a criou bateria na restrição. O
carregador confere antes e **passa adiante**, sem registrar nada.

Adotar a linha do cliente como semente seria a saída fácil e a errada: o registro diria que
aquela linha é nossa, e o `fingerprint` — calculado sobre valores que não escrevemos —
acusaria divergência na primeira conferência. O que não foi semeado não entra no registro.

### 8. O que efetivamente embarca agora

**Só as unidades raiz do `comercial`:** `Unidade (UN)`, `Quilograma (KG)` e `Litro (L)`.

Nada além disso, e a razão é a regra 6 do `CLAUDE.md`. "Caixa com 12" e "fardo com 10
caixas" parecem semente óbvia e são suposição: o fator muda por produto e por fornecedor,
e errado ele contamina todo cálculo de saldo. Categoria por segmento tem o mesmo problema
— as categorias de um supermercado não saem de dedução, saem do discovery, que para a
distribuidora é a Fase 4.

A semente que embarca é pequena de propósito. O que esta decisão entrega é o mecanismo
correto; o conteúdo cresce quando houver documento real que o sustente.

## Consequências

- O perfil passa a **configurar**, e não só instalar — modestamente nesta versão, com três
  unidades raiz. A lacuna 4.3 do benchmark fecha pelo mecanismo, e sai da §4.
- São três portas invertidas agora (verificação de ativação, reconciliação de permissão,
  carga de semente). O padrão deixou de ser caso isolado e passa a ser a resposta do
  projeto para "o host precisa de conhecimento que é do módulo". Merece parágrafo próprio
  em `docs/ARCHITECTURE.md` §2.
- A carga pela vitrine **não escreve na trilha de auditoria**, e isso é consistência e não
  descuido: ativar e desativar módulo também não escrevem. `seed_record` guarda o quê e o
  quando; falta o quem. Entra junto quando a trilha cobrir os fluxos de ativação, que é
  pendência própria no `ROADMAP.md`.
- Cada linha semeada custa uma linha de registro. É barato, e é o preço de poder responder
  "isto veio de semente ou o cliente criou?", que hoje não tem resposta.
- A suíte prova os casos de **não-escrita**, que são o motivo de o mecanismo existir:
  reativar não duplica; linha semeada que o cliente apagou não volta; linha renomeada não
  é recriada; o `fingerprint` acusa o ajuste do cliente; e unidade criada à mão não é
  reivindicada. Em banco real — `modules/core/tests/test_seed.py`.
- Carregador se registra na **importação** do pacote do módulo. Isso obriga quem dispara
  ativação fora da aplicação web a importar os módulos primeiro, e por isso o comando
  `decko-admin` passou a chamá-lo (`decko.modules.import_packages`). Sem esse cuidado,
  cadastrar empresa com `--module comercial` a deixaria sem semente, e em silêncio.
- Teste que montava à mão o que a semente agora entrega precisou mudar: `test_pdv_api` e
  `test_produto_fiscal_api` criavam a unidade "Unidade" e passaram a usá-la. A colisão
  apareceu na suíte, que é onde devia aparecer.

## Alternativas consideradas

**Semente declarada no `profiles/*.toml`** — descartado. O perfil escreveria em tabela de
módulo, contra a ADR 0007 e `ARCHITECTURE.md` §2, e a mesma árvore de unidades seria
copiada em cada perfil, para divergir no primeiro ajuste.

**Semente no módulo dono, organizada por segmento** (`comercial` trazendo as categorias de
"supermercado") — descartado. A base passaria a conhecer as verticais, que é exatamente a
dependência invertida: o peso do Odoo está na base justamente porque a vertical é fina.

**Reconhecer a semente pelo nome, sem tabela de registro** — descartado. O cliente renomeia
"Unidade" para "Un" e a reativação cria uma duplicata; e o nome não distingue "o cliente
apagou" de "nunca existiu", que é a distinção da decisão 4.

**Copiar o `noupdate` do Odoo** — descartado pela decisão 5. Ele pede ao autor do módulo
uma previsão sobre o cliente que o `fingerprint` obtém por conferência.

**Apagar a semente na desativação, como a desinstalação do Odoo** — descartado pela
decisão 6. Contraria a ADR 0004, e a chave estrangeira `RESTRICT` recusaria de todo modo
qualquer linha em uso.

**Semente dentro da migração Alembic** — descartado, e é a tentação mais próxima. Migração
é schema: roda uma vez por banco, e a semente é por empresa, aplicada num evento de tempo
de execução (a contratação do módulo). Semente em migração alcançaria empresa que não
contratou o módulo, não teria como ser removida, e misturaria dado de cliente com
versionamento de estrutura.
