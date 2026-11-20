# ADR 0026 — Consumo interno: módulo `custos`, e o valor é cópia, não avaliação de estoque

- **Data:** 2026-11-20
- **Status:** aceito
- **Completa:** `docs/adr/0025-centro-de-custo.md`, decisão 2
- **Relacionado:** `docs/adr/0006-base-comercial.md`, `docs/adr/0007-dependencia-entre-modulos.md`

## Contexto

O centro de custo já existe e a despesa já aponta para ele. Falta a outra metade da
pergunta *"quanto custou o hectare"*: o que **saiu do estoque** sem ser venda — o adubo que
foi para o talhão, o diesel que foi para o trator, a vacina que foi para o lote de bezerros.

O ADR 0025 decidiu que o `comercial` **não** passa a depender do `financeiro`, e que quem
registra o consumo é a camada de cima. Faltava dizer qual camada, já que `fazenda` ainda não
existe e o consumo interno não é exclusividade de fazenda: restaurante consome insumo,
loja consome embalagem, oficina consome peça.

## Decisão 1 — Um módulo `custos`, e não dentro do `financeiro`

`custos` depende de `core`, `comercial` e `financeiro`. Ele pede a saída de estoque ao
`comercial` e aponta para o centro de custo do `financeiro` — nunca escreve na tabela de
nenhum dos dois, pela regra do ADR 0007.

**Por que não dentro do `financeiro`:** porque o `financeiro` hoje depende só do `core`, e
é o módulo mais leve que resolve algo sozinho — quem quer apenas saber o que vence instala
um módulo e pronto. Pôr consumo lá dentro obrigaria essa empresa a instalar catálogo e
estoque inteiros para ver contas a pagar.

**Por que não dentro do `comercial`:** inverteria a direção de dependência, que é o que o
ADR 0025 decidiu evitar.

**Por que não esperar o `fazenda`:** porque o consumo interno não é agro. Fazer dentro da
fazenda obrigaria restaurante e oficina a instalar um módulo rural para lançar o que
gastaram, ou a esperar por ele.

## Decisão 2 — O consumo é uma **anotação** sobre o movimento, e não um movimento paralelo

`custos_consumo` guarda a ligação `movimento_id → centro_custo_id`, com o valor. Um
movimento tem no máximo um consumo, garantido por índice único.

A quantidade, o produto, o lote e a data **não são copiados**: eles estão no movimento, e
duplicá-los criaria duas verdades que divergem na primeira correção. O relatório paga um
`join`, que é o preço certo.

É o mesmo arranjo com que a pulverização dá baixa em defensivo: quem precisa do efeito
chama o serviço do `comercial` e guarda só o que é seu.

## Decisão 3 — O valor é **cópia do preço de custo**, e isso precisa estar dito

`Produto.preco_custo` é uma referência — o último custo conhecido —, e não o resultado de
uma avaliação de estoque. O consumo copia esse número no instante do lançamento, do mesmo
jeito que a venda copia o preço (ADR 0008) e a cobrança copia o valor do plano (ADR 0013).

**Isto não é PEPS, não é custo médio e não é contabilidade.** Avaliação de estoque é um
assunto inteiro, com método a escolher e efeito fiscal, e não há requisito escrito. Chamar
a cópia de "custo real" seria dar ao número uma autoridade que ele não tem — e alguém
fecharia uma safra em cima disso.

Daí duas consequências que estão no modelo:

- `custo_unitario` fica **gravado junto**, e não deduzido do produto na leitura. O preço de
  custo muda; o consumo do mês passado não deve mudar com ele.
- Quem informa `valor` na mão manda nele. O produto sem `preco_custo` exige o valor
  informado, em vez de lançar zero em silêncio — zero é um número, e um número errado
  estraga mais do que um campo vazio.

## Decisão 4 — O centro de custo é **obrigatório** no consumo

Na despesa ele é opcional, porque quem só quer saber o que vence não precisa classificar.
Aqui não: um consumo sem centro é uma linha que não responde nada, e o módulo inteiro
existe para responder contra o quê.

Quem não quer classificar simplesmente não instala `custos` — a saída de estoque continua
possível pelo `comercial`, como sempre foi.

## Decisão 5 — O relatório de custo por centro mora aqui, e soma as duas fontes

`custos` é o único módulo que enxerga despesa e consumo ao mesmo tempo, então é ele que
responde *"quanto custou a lavoura neste período"* — somando o que saiu do estoque e o que
foi pago em despesa, por centro.

O resumo do `financeiro` continua sendo só de despesa, e é correto que seja: ele não conhece
estoque e não deve passar a conhecer.

Como sempre, **soma na consulta** e nunca saldo guardado (ADR 0014, decisão 6).

## Fora de escopo

- **Avaliação de estoque** (PEPS, custo médio, custo de reposição). Ver a decisão 3.
- **Rateio de um consumo entre centros.** Meio caminhão de adubo em dois talhões é duas
  linhas hoje. Rateio por percentual tem regra própria e ninguém pediu.
- **Devolução de consumo.** O que voltou do talhão é entrada de estoque com motivo, e
  anular o consumo seria reescrever o passado — mesma regra da despesa paga.
- **Mão de obra e hora de máquina como custo.** São custos reais do hectare e **não** saem
  do estoque; entram quando houver requisito escrito, provavelmente com `frota` e com o
  controle de diária.

## Consequências

- A fazenda passa a ter as duas metades de *"quanto custou o hectare"* antes do módulo
  `fazenda` existir, e qualquer vertical ganha o mesmo.
- Mais um módulo para instalar, e é assumido: é o preço de não obrigar quem quer uma coisa
  a carregar a outra.
- O número que o relatório mostra é uma estimativa declarada, não um custo contábil. Está
  escrito na decisão 3 para não virar surpresa.
