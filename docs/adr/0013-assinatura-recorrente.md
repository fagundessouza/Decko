# ADR 0013 — Assinatura recorrente

- **Data:** 2026-10-30
- **Status:** aceito
- **Depende de:** ADR 0007 (dependência entre módulos)
- **Requisitos:** `docs/discovery/assinaturas-dois-modulos.md`, seções 3 e 5

## Contexto

O modelo de negócio mudou: o Decko passa a ser vendido por assinatura fechada, e quem
escreve o sistema é o primeiro a precisar cobrar por ele. O requisito veio com a regra de
inadimplência inteira — aviso, cinco dias, bloqueio, e um prazo de confiança concedido à
mão.

## Decisão

### 1. Módulo próprio, `assinaturas`, dependendo de `clientes`

Uma assinatura pertence a alguém, e esse alguém já tem cadastro. `depends = ["core",
"clientes"]`, pela ADR 0007.

**Não depende de `comercial`.** Assinatura aqui é serviço: não há mercadoria, não há baixa
de estoque — foi respondido no discovery. Quando alguém pedir cesta mensal, aí sim entra a
dependência, e será outra decisão.

### 2. Três tabelas, e o ciclo é linha, não cálculo

`assinaturas_plano`, `assinaturas_assinatura`, `assinaturas_cobranca`.

A cobrança de cada mês é **uma linha gravada**, não um período deduzido na leitura. A razão
é a mesma do estoque e da trilha: o que foi cobrado em março precisa continuar sendo o que
foi cobrado em março, mesmo que o preço do plano mude em abril. O valor é **copiado** para
a cobrança no momento em que ela nasce.

É a mesma distinção da venda identificada (ADR 0008): preço é fato histórico e se copia;
nome de pessoa é cadastro e se lê na hora.

### 3. O estado de acesso é **derivado**, não guardado

`em_dia`, `em_aviso`, `bloqueada` não são coluna. São função da cobrança mais antiga em
aberto e da data de hoje.

Guardar o estado exigiria alguém passando para atualizá-lo, e entre uma passada e outra ele
estaria errado — bloqueando quem pagou ontem ou liberando quem venceu hoje. Derivado, ele
nunca mente, e o custo é uma consulta que já traz a cobrança junto.

O prazo de confiança entra nessa função como uma data que empurra o bloqueio.

### 4. O prazo de confiança é ato de gente, com fim e com rastro

Três colunas na cobrança — até quando, por quê, e quem concedeu — e uma entrada na trilha
de auditoria a cada concessão.

- **Nunca automático.** Prazo que o sistema dá sozinho não é confiança, é outro prazo fixo,
  e aí os cinco dias viram seis.
- **Sempre com data de fim.** Prazo sem fim é perdão de dívida com outro nome.
- **Só vale para frente.** Conceder prazo para uma cobrança já paga não faz sentido e é
  recusado.
- **A concessão nova substitui a anterior**, e a trilha guarda as duas. O histórico mora
  onde mora histórico, não numa quarta tabela.

### 5. Bloquear marca o estado; não fecha porta nenhuma

E isso é limite declarado, não omissão. `assinaturas` não escreve em `core.tenant` (ADR
0007), e suspender uma empresa é ato do núcleo. Além disso, os clientes da Decko ainda não
existem como empresas num sistema no ar — falta tudo o que `docs/NEGOCIO.md` §5.1 lista.

O módulo responde **quem deveria estar bloqueado**. Transformar a resposta em porta fechada
é trabalho do núcleo, depois.

### 6. Sem gateway, e o desenho não espera por um

A cobrança nasce aberta e é **marcada como paga à mão**, com data e forma. É o que o
`ROADMAP.md` já previa, e serve a quem recebe por Pix manual ou boleto — que é o caso hoje.

Quando houver gateway, ele entra como **quem confirma o pagamento**, não como outro modelo:
a cobrança continua sendo a mesma linha, e ganha a origem da confirmação.

### 7. Cobra por empresa, não por usuário nem por módulo

Assumido para esta versão, porque a pergunta 6 do discovery segue aberta e a resposta mais
simples é a que não inventa estrutura. Um plano tem um preço; uma empresa assina um plano.

Preço por usuário ou por módulo muda o modelo de dados, e muda depois de alguém pedir.

## Consequências

- A Decko passa a ter perfil próprio (`profiles/decko.toml`): clientes e assinaturas. O
  dono do produto usa o produto, que era o pedido.
- A trilha de auditoria ganha ações novas: cobrança paga, prazo concedido, assinatura
  cancelada. Ela já existe e já é lida por tela.
- Gerar a cobrança do mês é operação explícita, não tarefa agendada. Agendador é
  infraestrutura que o projeto ainda não tem, e fingir que tem seria pior.

## Alternativas consideradas

**Guardar o estado da assinatura numa coluna** — descartado pela decisão 3. Exigiria um
processo para mantê-la verdadeira, e entre duas execuções ela estaria errada.

**Calcular o período em vez de gravar a cobrança** — descartado. O preço muda, e um
histórico que se recalcula deixa de ser histórico.

**Uma tabela de prazos concedidos** — descartado pela decisão 4. O histórico de concessões
é exatamente o que a trilha de auditoria guarda, e uma quarta tabela duplicaria isso para
responder a mesma pergunta.

**Bloquear de verdade, suspendendo o tenant** — descartado pela decisão 5. Atravessaria a
fronteira entre módulos, e não haveria a quem cortar.
