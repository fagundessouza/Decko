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

1. **O caixa é por operador ou por terminal?** Hoje não existe entidade de terminal — duas
   máquinas do mesmo operador são indistinguíveis. A mesma lacuna já foi registrada no
   discovery fiscal, porque o cupom precisa identificar o caixa.
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
