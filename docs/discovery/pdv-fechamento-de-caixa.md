# Discovery — fechamento de caixa

**Última revisão:** 10/11/2026.

O `ROADMAP.md` carrega "abertura e fechamento de caixa (sangria, suprimento, conferência)"
como item sem requisito desde a ADR 0008. Este documento separa o que **já está decidido**,
o que **dá para fazer sem resposta nenhuma**, e o que **continua travado** — para a parte
travada não ser construída por suposição.

## 1. O que já está decidido, e onde

Não é terreno virgem. A `docs/adr/0008-ponto-de-venda.md` decidiu três coisas que valem
aqui:

- **A conferência é cega.** O operador conta o dinheiro sem ver o valor esperado. É o que
  impede ajustar a contagem para bater, e é o ponto inteiro de conferir.
- **`pdv.venda.finalizar` já é permissão separada de `pdv.venda.write`**, criada
  explicitamente para que "o caixa possa lançar sem poder fechar" quando houver requisito.
  A separação existe; falta a regra que a usa.
- **Saldo insuficiente não bloqueia venda.** "Deixar de vender é decisão comercial do dono,
  não do sistema. O lançamento fica na razão e a divergência aparece." O dono do projeto
  confirmou a mesma lógica para estoque em 04/11/2026, com outras palavras: *"se não bater
  a conta é aí que tá o pulo do gato"*.

A terceira é a mais importante para cá: **a divergência é o produto**. O fechamento existe
para mostrar que não bateu, não para impedir que não batesse.

## 2. O que a cliente pediu

Do `pdv-perifericos-e-pagamento.md`: é o relatório que a dona da distribuidora quer no fim
do dia. Nas palavras do dono do projeto, sobre o que ela teme:

> *"pra não ter caixa 2, pra não ter gente esquecendo de receber. Se houver, ele já sabe
> que teve algum problema no dia."*

Ou seja, o valor não está em travar nada: está em **quanto entrou, em quê, e por quem**.

## 3. O que dá para fazer sem resposta nenhuma

Somar o que já está registrado. Toda peça existe no banco hoje:

| Peça | Onde |
|---|---|
| Venda, com data de abertura e de fechamento | `pdv_venda` |
| Quem operou | `pdv_venda.operador_id` |
| Forma de pagamento e valor | `pdv_pagamento` |
| Em qual conta caiu | `pdv_pagamento.conta_id` (ADR 0014) |
| Desconto da venda e de cada item | `pdv_venda.desconto`, `pdv_venda_item.desconto` |

Um relatório por período responde a pergunta da cliente sem decidir nada sobre sessão de
caixa. **É o que está sendo construído agora.**

## 4. O que continua travado — e não se constrói sem resposta

A sessão de caixa em si. Cada pergunta abaixo muda o modelo, não a tela:

1. ~~**O caixa é por operador ou por terminal?**~~ **Respondida em 10/11/2026: por
   operador.** O caixa pertence a quem opera, não à máquina. Isso resolve a sessão sem
   precisar da entidade de terminal, que continua não existindo — e ela continua
   necessária para o **cupom fiscal**, que precisa identificar o caixa (CX). São duas
   lacunas diferentes, e só esta fechou.
2. **Vender exige caixa aberto?** Se exigir, esquecer de abrir trava o balcão na primeira
   venda do dia. Se não exigir, "caixa fechado" vira só um rótulo.
3. **Quem fecha?** A permissão `pdv.venda.finalizar` existe para separar isso, e ninguém
   decidiu se o operador fecha o próprio caixa ou se só o dono fecha.
4. **O que entra na conferência?** Só dinheiro em espécie, ou cartão e Pix também? Cartão
   não está na gaveta — conferir o que não se conta é ruído.
5. **Sangria e suprimento são do MVP?** São retirada e entrada de dinheiro fora de venda.
   Sem eles, o esperado nunca bate numa loja que tira dinheiro durante o dia.
6. **O que acontece quando não bate?** Registra e segue, exige justificativa, ou impede o
   fechamento? A ADR 0008 e o dono do projeto apontam para "registra e mostra", mas isso
   não foi dito sobre caixa.

Nenhuma dessas foi respondida. Até lá, o relatório da seção 3 entrega o valor que a cliente
descreveu, e a sessão espera.

---

## 5. Proposta derivada — aguardando confirmação

Com o caixa sendo por operador, as outras cinco perguntas deixam de ser independentes:
quase todas já têm resposta implícita em decisões que este projeto tomou e escreveu. O que
está abaixo **não é suposição**, é dedução a partir delas — mas segue como proposta até o
dono do projeto confirmar, porque deduzir não é o mesmo que perguntar.

**Vender não exige caixa aberto.** A ADR 0008 já decidiu o princípio no caso vizinho: *"deixar
de vender é decisão comercial do dono, não do sistema (...) travar por padrão pararia o
balcão."* Um caixa esquecido de abrir na segunda-feira de manhã não pode parar a fila. A
venda sem caixa aberto fica registrada e aparece na conferência como **fora de sessão**, que
é informação, não bloqueio.

**Quem fecha é quem tem permissão para fechar.** A ADR 0008 já separou `pdv.venda.finalizar`
de `pdv.venda.write` exatamente para "o caixa poder lançar sem poder fechar". A sessão segue
o mesmo padrão, com uma permissão própria — `pdv.caixa.fechar` —, e cabe a cada loja dar ou
não ao operador.

**Sangria e suprimento entram.** Não por completude: sem eles o esperado nunca bate numa
loja que tira dinheiro durante o dia, e um número que nunca bate deixa de ser conferido na
segunda semana. São o que torna a conferência utilizável, e já aparecem citados na tela
atual como a causa provável de uma diferença.

**Não bater nunca impede o fechamento.** É a mesma regra do estoque, que o dono do projeto
deu em 04/11/2026: *"se não bater a conta é aí que tá o pulo do gato"*. A divergência é
registrada com o valor contado, o esperado e a diferença, e fica no histórico. Esconder ou
travar destruiria o único dado que a conferência produz.

**O que se conta continua sendo só o dinheiro.** Já é o comportamento da tela, e a razão não
mudou: cartão e Pix não estão na gaveta. Fica em aberto apenas se alguma loja quiser
conferir a maquininha — e isso é requisito de quem pedir, não desenho antecipado.

### A última, respondida em 10/11/2026

**Venda feita fora de sessão fica listada à parte.** Não é absorvida pela sessão aberta
depois.

A razão é a mesma que sustenta o resto: a sessão responde "o que passou por este caixa,
entre abrir e fechar". Puxar para dentro dela uma venda que aconteceu antes de ela existir
faria o fechamento mentir sobre o próprio período — e a diferença apareceria num caixa que
não a produziu. Listada à parte, a venda continua contada no dia, visível, e sem
contaminar a conferência de ninguém.

Tem um efeito colateral desejável: **caixa esquecido aberto vira visível**. Se as vendas
fora de sessão forem muitas num dia, isso é exatamente o sintoma de que ninguém está
abrindo o caixa — e o relatório mostra, em vez de esconder dentro de uma sessão qualquer.

---

## 6. Situação

| Pergunta | Estado |
|---|---|
| 1. Por operador ou por terminal | **Respondida:** por operador |
| 2. Vender exige caixa aberto | Deduzida: não exige |
| 3. Quem fecha | Deduzida: permissão `pdv.caixa.fechar` |
| 4. O que se conta | Deduzida: só espécie |
| 5. Sangria e suprimento | Deduzida: entram |
| 6. O que acontece quando não bate | Deduzida: registra, nunca trava |
| 7. Venda fora de sessão | **Respondida:** listada à parte |

As deduzidas vêm de decisões escritas da ADR 0008 e do próprio dono do projeto, e esperam
o **de acordo** dele antes de virarem código.
