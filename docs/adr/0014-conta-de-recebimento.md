# ADR 0014 — Conta de recebimento

- **Data:** 2026-10-30
- **Status:** aceito
- **Depende de:** ADR 0007 (dependência entre módulos), ADR 0008 (ponto de venda)
- **Requisitos:** `docs/discovery/pdv-perifericos-e-pagamento.md`

## Contexto

A dor veio de uma cliente real, e é de conferência de caixa no fim do expediente:

> *"Não sabia o que entrava por cartão de crédito e o que entrava pelo débito, o que era
> Pix em qual conta — porque às vezes ela recebia o Pix em uma conta ou em outra."*

O Decko já distingue **como** o cliente pagou: `FormaPagamento` separa dinheiro, débito,
crédito e Pix. O que ele não sabe dizer é **para onde o dinheiro foi**. Duas chaves Pix da
mesma loja são dois destinos diferentes, e no fim do dia é isso que não fecha.

O pedido original vinha embrulhado em maquininha, Bluetooth e porta serial. O discovery
separou a dor do remédio: **esta parte é software puro**, não depende de hardware,
adquirente nem agente local.

## Decisão

### 1. Módulo próprio, `financeiro`

A conta de recebimento não é do ponto de venda. O PDV é um consumidor; o outro já existe
(a baixa de cobrança em `assinaturas` tem a mesma pergunta sem resposta), e o roadmap traz
um terceiro: abertura e fechamento de caixa.

Colocá-la em `comercial` seria errado de outra forma — aquele módulo é catálogo e estoque,
e `assinaturas` não depende dele nem deve passar a depender.

### 2. O PDV declara `financeiro` em `depends`

Instalar o ponto de venda traz o cadastro de contas junto, como já traz a base comercial e
o cadastro de clientes.

O custo é o mesmo das outras duas vezes, e é assumido pela mesma razão: acoplamento entre
módulos irmãos tem resposta decidida na ADR 0007 — declarar. Uma porta invertida aqui seria
construir para um "PDV sem contas" que ninguém pediu.

### 3. A conta no pagamento é **opcional**

`pdv_pagamento.conta_id` é nulo por padrão, e nada no caixa trava por causa dele.

Velocidade de balcão é requisito funcional do projeto, não preferência. Um campo
obrigatório a mais por pagamento é fila parada — e a loja que tem uma conta só não ganha
nada preenchendo sempre a mesma. Quem quer a conferência separada preenche; quem não quer,
vende como antes.

### 4. A chave estrangeira é `RESTRICT`, e conta não se apaga

Conta desativada some das escolhas novas e continua existindo para as vendas antigas. É a
mesma regra do cadastro de clientes, e pela mesma razão: o que já aconteceu continua
apontando para alguém.

### 5. A conta é de **recebimento**, não um plano de contas

Nome, instituição e chave Pix. Nada de saldo, extrato, conciliação ou lançamento contábil.

Isso é limite declarado: a dor descrita é *"em qual conta caiu"*, e responder isso não exige
contabilidade. Plano de contas e conciliação bancária são outro produto, e entram quando
houver requisito escrito — não porque a tabela "já estava quase lá".

### 6. Não guarda saldo

Pelo mesmo motivo do estoque e do estado da assinatura: saldo guardado precisa de alguém
mantendo verdadeiro, e entre duas passadas está errado. Quanto entrou em cada conta é soma
dos pagamentos, e sai da consulta.

## Consequências

- A conferência de fim de dia passa a ser possível por consulta, em vez de por recibo na
  mão. O relatório em si é o **fechamento de caixa**, que continua sem requisito escrito no
  `ROADMAP.md` — esta decisão entrega o dado que falta a ele.
- `assinaturas` ganha a mesma possibilidade e **não a usa ainda**: a baixa de cobrança
  continua com `forma_pagamento` em texto. Ligar as duas é uma linha, e fica para quando
  alguém pedir — está escrito aqui para não virar esquecimento.
- Empresa que já tinha o PDV sem `financeiro` não recebe o módulo sozinha, pela mesma regra
  da ADR 0010: a tela oferece a escolha de conta só quando o módulo está ativo.

## Alternativas consideradas

**Um campo de texto livre no pagamento** ("Nubank", "BB") — descartado. Texto livre vira
`Nubank`, `nubank`, `NuBank` e `Nu` na mesma loja, e a soma do fim do dia não fecha, que é
exatamente o problema que se foi resolver.

**A conta pendurada na forma de pagamento** (todo Pix cai sempre na mesma conta) —
descartado porque contraria o caso descrito: *"às vezes ela recebia o Pix em uma conta ou
em outra"*. Seria o modelo respondendo uma pergunta mais fácil que a real.

**Conta obrigatória no pagamento** — descartado pela decisão 3. Travaria o balcão de quem
não precisa da separação.

**Guardar saldo na conta** — descartado pela decisão 6.
