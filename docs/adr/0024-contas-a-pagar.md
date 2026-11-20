# ADR 0024 — Contas a pagar: a despesa mora no `financeiro`, e a conta deixa de ser só de recebimento

- **Data:** 2026-11-20
- **Status:** aceito
- **Estende:** `docs/adr/0014-conta-de-recebimento.md`
- **Pedido por:** `docs/discovery/agro-gestao-da-fazenda.md`, seção 5, item 12

## Contexto

O `financeiro` sabia para onde o dinheiro **entra** e não sabia nada sobre o que **sai**. A
falta apareceu primeiro no levantamento da fazenda — uma propriedade rural é, em dinheiro,
quase só saída —, mas não é problema do agro: energia, aluguel, fornecedor e financiamento
vencem em qualquer vertical, e nenhuma delas tinha onde registrar isso.

O caso mais concreto, do levantamento: *"quais contas vencem todo mês sem falta — energia,
arrendamento, financiamento?"*. Responder isso é a função mínima.

## Decisão 1 — A despesa mora no `financeiro`, e não num módulo novo

É a mesma pergunta — o dinheiro — vista dos dois lados do caixa. Separar em um módulo
"contas a pagar" obrigaria a empresa a ligar dois módulos para ter meio financeiro cada, e
a conta bancária ficaria num e a despesa no outro.

## Decisão 2 — A conta deixa de ser só de recebimento, e a classe é renomeada

A baixa da despesa aponta **de qual conta o dinheiro saiu**, e é a mesma conta onde ele
entra: a loja tem um Nubank PJ, não um Nubank-de-entrada e um Nubank-de-saída.

A tabela já se chamava `financeiro_conta` — genérica. Quem mentia era a classe Python,
`ContaRecebimento`, e ela foi renomeada para `Conta`. É renomeação de código, sem migração:
nenhuma coluna muda.

**Por que não deixar como estava:** porque o próximo a ler o código veria dinheiro saindo
de uma "conta de recebimento" e concluiria, corretamente, que alguém tinha empurrado um uso
para dentro de um nome que não cabia. O projeto já paga esse juro em `agro_client` e
`agro_product`.

O vínculo é **opcional** e `RESTRICT`, pelas mesmas decisões 3 e 4 do ADR 0014: quem não
separa contas não precisa escolher, e conta que já pagou algo não se apaga.

## Decisão 3 — Fornecedor é texto, não cadastro

A despesa guarda `fornecedor_nome` e `fornecedor_cpf_cnpj` como texto, no mesmo padrão de
`comercial_produto_fornecedor`.

**Isto parece contradizer o ADR 0014**, que descartou texto livre para a conta justamente
porque `Nubank`, `nubank` e `Nu` não somam. A diferença é a pergunta: lá, a soma **era** por
conta, e texto livre quebrava o fechamento do dia. Aqui a pergunta é *"quanto sai este
mês"*, que soma por **vencimento** — e nenhuma grafia de fornecedor atrapalha isso.

Cadastro de fornecedor entra quando aparecer requisito escrito de relatório **por
fornecedor**. Antes disso seria tabela criada para caso hipotético.

## Decisão 4 — O status é gravado, e a despesa paga não volta atrás

`aberta`, `paga`, `cancelada` — o mesmo conjunto de `assinaturas.Cobranca`, e de propósito:
é a mesma forma (algo devido, com vencimento, que vira pago ou não será pago), e inventar
um vocabulário diferente para a mesma coisa só faria quem lê ter de aprender duas vezes.

Transições permitidas: `aberta → paga` e `aberta → cancelada`. **Despesa paga não é
cancelada nem reaberta.** Dinheiro que saiu, saiu; desfazer é um estorno, que é outro
registro e ainda não tem requisito escrito. Cancelada também não volta: lançar de novo é
uma linha nova, e ela conta a verdade melhor do que um campo mudando de ideia.

## Decisão 5 — O que se deve e o que se pagou são dois valores

`valor` é o que estava na conta; `valor_pago` é o que de fato saiu, e é gravado na baixa.
Eles diferem o tempo todo — juros por atraso, desconto por antecipação, multa.

Tratar os dois como um só é o tipo de simplificação que parece limpa e depois impede a
única conferência que interessa: *"paguei mais do que devia este mês, e em quê?"*. Quando a
baixa não informa `valor_pago`, ele recebe o `valor` — o caso comum não dá trabalho.

## Decisão 6 — Continua sem guardar saldo

A decisão 6 do ADR 0014 vale igual: *"quanto sai este mês"* é soma na consulta, não um
número guardado que alguém precisa manter verdadeiro.

## Fora de escopo, declarado

Nenhum destes é esquecimento, e nenhum entra sem requisito escrito:

- **Recorrência.** Energia vence todo mês, e lançar doze linhas à mão é trabalho. Mas
  recorrência tem regras próprias — o que acontece quando o valor muda, quando se cancela a
  série, quando um mês é diferente — e isso é um ADR inteiro.
- **Centro de custo.** A fazenda precisa saber contra qual talhão a despesa foi, e o ADR
  0023 já decidiu que esse apontamento existe. Ele entra com a fatia da fazenda, e vale
  para o consumo de estoque também — não é coisa só de despesa.
- **Parcelamento.** Uma compra em 3x são três despesas com vencimentos diferentes. Hoje se
  lança as três; gerar automaticamente é conveniência, não função que falta.
- **Conciliação bancária, plano de contas e anexo de boleto.** Mantidos fora pela decisão 5
  do ADR 0014.
- **Contas a receber fora do PDV.** Fiado e crediário são outra coisa, e o PDV já registra
  o que vendeu.

## Consequências

- O `financeiro` passa a responder a pergunta que a fazenda faz e que toda loja também faz,
  e deixa de ser o módulo de uma tabela só.
- `pdv` importa `Conta` em vez de `ContaRecebimento`; é a única mudança fora do
  `financeiro`, e os testes dele cobrem o caminho.
- A tela ainda não existe: esta fatia é modelo, regra e API. O menu do sistema continua
  dizendo "Contas de recebimento" até a tela de despesas entrar, e o rótulo do módulo já
  foi corrigido para "Financeiro" no manifesto.
- Baixar é permissão própria, `financeiro.despesa.baixar`, separada de `write`: registrar
  que uma conta existe não é a mesma autoridade que declarar que ela foi paga — mesma
  separação de `pdv.caixa.fechar` e de `assinaturas.cobranca.baixar`.
