# Discovery — devolução de venda

**Última revisão:** 10/11/2026.

A `docs/adr/0008-ponto-de-venda.md`, decisão 6, recusa cancelar venda finalizada e diz por
quê: *"desfazer uma saída de estoque já lançada é devolução, que tem regra própria e
consequência fiscal"*. Este documento é a regra própria, escrita a partir do que o dono do
projeto respondeu em 10/11/2026 — não de suposição.

## 1. O que já estava decidido, e onde

Três decisões escritas governam a devolução antes de qualquer pergunta nova:

- **A razão de estoque não aceita edição do passado.** O `TipoMovimento.AJUSTE` do módulo
  comercial existe porque *"divergência vira lançamento novo, com motivo, e não um número
  reescrito"*. Logo a devolução **não estorna** a saída da venda: ela lança uma **entrada**.
- **A venda finalizada é congelada.** Preço, descrição e total são cópia justamente para
  que o cupom continue dizendo o que o cliente pagou (ADR 0008, e o comentário em
  `ItemVenda.preco_unitario`). A devolução é documento novo que **aponta** para a venda, e
  nunca altera a venda.
- **O servidor é que faz a conta.** ADR 0008, decisão 3: *"duas somas do mesmo valor em
  lugares diferentes divergem, e a que o cliente paga é a do servidor"*. O valor a devolver
  é calculado, não digitado — valor de reembolso digitado à mão é onde a fraude mora.

## 2. O que o dono do projeto respondeu em 10/11/2026

**Pergunta: como o dinheiro volta ao cliente?**

> Espécie, descontando da gaveta.

**Pergunta: o produto devolvido volta ao estoque vendável?**

> *"O interessante é que volte sem causar complicações e transtornos, o problema é quando é
> RMA, tem que ter algum jeito de informar que é problema, defeito ou algo assim. Pra
> separar no estoque as trocas e avarias ou algo assim."*

A segunda resposta é requisito novo, e não confirmação: **voltar é o caminho normal, e
defeito tem de ser dito.**

## 3. As decisões que saem disso

### 3.1. Cada linha devolvida tem um destino

Duas opções, e só duas:

| Destino | O que acontece no estoque |
|---|---|
| `estoque` | Volta vendável: **entrada** na razão, com o documento da devolução |
| `avaria` | Não volta: **nenhum** lançamento, e a linha fica somada na lista de avarias |

O destino é **por linha**, não por devolução: o cliente que traz três garrafas e uma
quebrada faz uma devolução só, com duas linhas e dois destinos.

`estoque` é o padrão da tela, porque é o caso comum — "que volte sem causar complicações".

### 3.2. "Separar no estoque" não pode ser depósito, e por quê

Não existe entidade de local, depósito ou armazém no módulo `comercial`: há produto, lote,
unidade e razão. Um segundo depósito contado na razão seria **entidade nova**, com decisão
própria (transferência entre locais, saldo por local, contagem por local) — e nada disso
tem requisito escrito.

A separação sai sem inventar entidade: o item com defeito **não entra no estoque
vendável**, então o saldo continua verdadeiro, e a lista de avarias do período diz o que
está parado — produto, quantidade e o motivo que o operador escreveu. Separado na prática,
e sem um número de estoque que mentiria sobre o que dá para vender.

### 3.3. Devolução em espécie sai da gaveta

A forma da devolução é registrada, e **só espécie mexe no caixa**: o esperado da sessão
passa a ser `abertura + espécie recebida + suprimentos − sangrias − devoluções em espécie`.
Cartão e Pix ficam registrados na forma original e o estorno é da adquirente — o sistema
não tem como mandar a maquininha devolver, e finge que tem seria pior do que não ter.

A sessão é anexada pela mesma regra da venda: a devolução cai no caixa aberto **do
operador**, e quando não há caixa aberto ela fica **fora de sessão** — registrada, visível,
e sem contaminar a conferência de ninguém. É a decisão de 10/11/2026 sobre venda fora de
sessão, valendo para o dinheiro que sai.

### 3.4. O que mais vem das decisões antigas, sem pergunta nova

- **Permissão própria `pdv.venda.devolver`**, pelo mesmo motivo que `pdv.venda.finalizar` e
  `pdv.caixa.fechar` existem: a loja decide se quem opera o balcão também devolve dinheiro.
- **Motivo obrigatório**, pela razão da sangria: *"retirada que ninguém explica depois é
  justamente a que importa explicar"*.
- **Parcial por linha e por quantidade.** O item já guarda quantidade decimal; devolver 2
  de 5 garrafas não exige modelo novo, e proibir isso seria inventar restrição.
- **Não se devolve mais do que se vendeu.** Somando todas as devoluções daquela linha. Isso
  é aritmética, não política — e quem recusa é o serviço, com o nome do produto e o que
  ainda resta.
- **A venda continua `finalizada`.** Devolvida não é status: é soma das devoluções dela.
  Estado que se calcula não diverge do fato que o produziu (ADR 0013).

### 3.5. Como o valor é calculado

O desconto da venda inteira não está nas linhas, então a linha não pode ser devolvida pelo
seu próprio total: devolveria mais do que o cliente pagou. O fator é o que a venda
realmente custou sobre a soma das linhas:

```
fator = venda.total / soma(itens.total)
valor = (item.total / item.quantidade) × quantidade_devolvida × fator
```

Numa venda de R$ 100 em itens com R$ 10 de desconto, devolver um item de R$ 20 devolve
R$ 18 — que é o que aquele item custou ao cliente.

## 4. O que fica de fora, de propósito

- **Documento fiscal de devolução.** Tem CFOP próprio e é nota de entrada. Não existe
  emissão fiscal no projeto (ADR 0008 e `docs/adr/0018-modelo-fiscal-em-transicao.md`), e
  devolução sem nota é exatamente o que a loja já faz hoje no caderno. Entra com o módulo
  fiscal, que tem a tabela certa. A pergunta 4 de
  `docs/discovery/comercial-entrada-por-nota.md` já guarda o CFOP de devolução.
- **Controle de RMA junto ao fornecedor.** A lista de avarias diz o que está parado; ela
  **não** acompanha o que já foi mandado de volta, trocado ou creditado. Fechar esse ciclo
  depende do fornecedor como entidade, que é o outro item do roadmap — e aí sim vale a
  pena, porque o ciclo tem as duas pontas.
- **Crédito do cliente para abater em compra futura.** Foi oferecido e recusado na mesma
  conversa: exigiria entidade de crédito, com limite e vencimento, que não existe em
  `clientes` nem em `financeiro`. É o mesmo terreno de fiado e crediário, que a ADR 0008 já
  deixou fora.
- **Prazo de devolução e quem autoriza.** Política de loja. A permissão separada já permite
  que só o dono devolva; prazo vira configuração quando alguém pedir.
- **Devolução dividida em mais de uma forma.** Uma devolução tem uma forma. Loja que
  precisar devolver metade em espécie e metade no cartão registra duas — o que é mais
  honesto do que um rateio que ninguém pediu.
- **Troca como operação única.** Troca é devolução mais venda nova, e as duas já existem.
  Juntar numa tela só é conveniência, não regra, e espera alguém reclamar da fricção.

## 5. Situação

| Pergunta | Estado |
|---|---|
| Como o dinheiro volta | **Respondida:** espécie sai da gaveta; cartão e Pix só registram |
| Produto volta ao estoque | **Respondida:** volta por padrão, defeito vai para avaria |
| Separação de avarias | **Respondida:** fora do estoque vendável, listada por produto |
| Valor a devolver | Deduzida: calculado no servidor, com o fator do desconto |
| Permissão | Deduzida: `pdv.venda.devolver`, separada |
| Parcial | Deduzida: por linha e por quantidade |
| Documento fiscal | **Fora:** depende do módulo fiscal |
| RMA com o fornecedor | **Fora:** depende do fornecedor como entidade |
