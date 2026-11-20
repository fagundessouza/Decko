# ADR 0025 — Centro de custo: lista plana no `financeiro`, e o `comercial` não é tocado

- **Data:** 2026-11-20
- **Status:** aceito
- **Estende:** `docs/adr/0024-contas-a-pagar.md`
- **Antecipa:** `docs/adr/0023-gestao-da-fazenda.md`, decisão 3

## Contexto

Contas a pagar respondem *"quanto sai este mês"*. Não respondem a pergunta seguinte, que é
a que o produtor faz no fim da safra e o lojista faz no fim do mês: **contra o quê o
dinheiro saiu.**

O ADR 0023 já tinha decidido que esse apontamento existe e que ele vale também para o
consumo de estoque. Faltava decidir **onde ele mora** — e isso precisa ser decidido agora,
porque a despesa está sendo construída e acrescentar o campo depois custa migração de dado.

## Decisão 1 — O cadastro mora no `financeiro`

Centro de custo é classificação de dinheiro, e a pergunta que ele responde é financeira.
Pôr o cadastro em cada vertical faria a fazenda ter os dela, a loja ter os dela, e a soma
da empresa não existir em lugar nenhum.

## Decisão 2 — O `comercial` **não** passa a depender do `financeiro`

A tentação é pendurar o centro de custo direto no movimento de estoque: o adubo que saiu já
diria contra qual talhão foi. Isso inverteria a direção do ADR 0007 — as verticais dependem
da base, e nunca o contrário —, e o `comercial` hoje depende só do `core`.

O caminho é o outro: **a vertical registra o consumo**, apontando para o movimento de
estoque que ela mesma pediu e para o talhão, o lote de gado ou a máquina. O centro de custo
sai daí. O `comercial` continua sabendo apenas que saiu mercadoria, que é o que ele precisa
saber.

Isso custa uma tabela a mais na vertical e mantém a base livre. É o mesmo arranjo com que a
pulverização dá baixa em defensivo hoje.

## Decisão 3 — Lista plana, e não árvore

Um centro de custo tem nome e nada mais. Sem pai, sem código contábil, sem nível.

Hierarquia é o começo do plano de contas, que a decisão 5 do ADR 0014 mantém fora de
propósito. E a lista plana já responde o que foi pedido: *lavoura*, *pecuária*, *frota*,
*administrativo* — ou, numa rede, *loja centro* e *loja bairro*. Árvore entra quando alguém
mostrar o relatório que ela precisa e a lista plana não dá; antes disso seria estrutura
criada para caso hipotético.

## Decisão 4 — Opcional na despesa, e `RESTRICT`

Quem não separa custo não precisa escolher — a mesma decisão 3 do ADR 0014, pelo mesmo
motivo: obrigar travaria quem só quer saber o que vence.

E centro que já tem despesa não se apaga: desativa. Senão o custo do ano passado perde o
nome, e o relatório histórico passa a mentir.

## Decisão 5 — O resumo quebra por centro

`GET /financeiro/despesas/resumo` passa a trazer, além dos totais, a soma por centro no
período. É aqui que a pergunta vira resposta — e continua sendo **soma na consulta**, nunca
saldo guardado, pela decisão 6 do ADR 0014.

A despesa sem centro aparece como "Sem centro de custo". Esconder esse grupo faria os
números não baterem com o total, e um relatório que não fecha é pior do que nenhum.

## Consequências

- A fazenda ganha metade do caminho para *"quanto custou o hectare"*. A outra metade é o
  consumo de estoque, que entra com o módulo `fazenda` — e já sabe onde pendurar.
- Qualquer vertical ganha custo por unidade de negócio sem módulo novo.
- O `comercial` fica como está, e a direção de dependência do ADR 0007 segue intacta.

## Fora de escopo

- **Rateio.** Uma conta de energia dividida entre lavoura e pecuária por percentual é outra
  coisa, com regra própria, e ninguém pediu.
- **Centro de custo em receita.** O PDV não aponta centro: a venda já tem produto e
  operador, e classificar receita é pergunta diferente da de custo.
- **Orçamento por centro.** Comparar gasto com o previsto exige o previsto, que não existe.
