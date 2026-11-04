# ADR 0017 — Meios de pagamento: um agregador por vez, atrás de uma porta

- **Data:** 2026-11-03
- **Status:** aceito
- **Depende de:** ADR 0004 (ativação de módulo por empresa), ADR 0007 (dependência entre
  módulos), ADR 0008 (ponto de venda)
- **Leia junto:** ADR 0014 (conta de recebimento) e
  `docs/discovery/pdv-perifericos-e-pagamento.md`, que ainda estão em revisão no PR
  [#12](https://github.com/fagundessouza/Decko/pull/12) e não chegaram ao tronco

## Contexto

Hoje o Decko **registra** pagamento, não **captura**. A tabela `pdv_pagamento` guarda uma
forma — `dinheiro`, `debito`, `credito`, `pix`, `outro` — e um valor, e nada no módulo
`pdv` conversa com adquirente, banco ou provedor. O operador olha a maquininha, vê que
aprovou, e digita no sistema.

Isso foi suficiente para abrir o caixa e continua suficiente para quem recebe em dinheiro.
Deixa de ser no momento em que a loja quer que a maquininha alimente o sistema sozinha, ou
que o QR code do Pix apareça na tela e a venda se feche quando o dinheiro cair.

A pergunta que este ADR responde não é *qual provedor*, e sim **quantos, e onde eles
moram**. Ela apareceu porque o mercado brasileiro tem muitos meios — Pix, boleto, as
bandeiras de cartão, carteiras digitais — e a tentação é integrar um a um.

A premissa que orientou a decisão é do dono do projeto, e está registrada como premissa
porque não foi medida aqui:

> *"Integrar um grande agregador (como Mercado Pago ou Pagar.me / Stone) que por si só já
> aceita Pix, boleto e as principais bandeiras de cartão de crédito/débito. Com apenas uma
> integração, você resolve 90% das necessidades do mercado brasileiro."*

## Decisão

**1. Um agregador por vez, não vários provedores lado a lado.**

A integração é com um agregador que já cubra Pix, boleto e as bandeiras principais. Somar
provedores multiplica o que precisa ser mantido, conciliado e explicado ao cliente quando
algo não cai — e não multiplica o que a loja consegue receber, porque o agregador já cobre.

**2. O provedor mora em módulo próprio, nunca no núcleo.**

O módulo se chama `pagamentos_<provedor>` e é instalável por empresa como qualquer outro
(ADR 0004). Quem não contratou não tem a rota montada, não tem a tabela povoada e não paga
o peso.

**3. O PDV não importa o módulo do provedor: chama uma porta.**

Pela ADR 0007, módulo só importa de quem declara em `depends`. Aqui nem isso: o `pdv` não
deve saber que provedor existe. O host declara a porta, o módulo do provedor se registra
ao ser importado — **a quarta porta invertida**, no mesmo padrão da guarda de ativação, do
reconciliador de permissões e do carregador de semente.

A consequência que importa: acrescentar um provedor novo não toca em uma linha do `pdv`.

**4. O registro continua sendo a verdade; a captura é um acréscimo.**

Uma transação capturada preenche `pdv_pagamento`, não substitui. O caixa precisa continuar
fechando venda quando o provedor está fora do ar, quando a internet cai e quando o
pagamento é em dinheiro — que não tem provedor e nunca vai ter. Capturado e digitado
convivem na mesma venda.

**5. Dinheiro continua somado no servidor.**

A ADR 0008, decisão 3, não muda: total, falta e troco vêm do servidor. Valor que chega do
provedor entra por lá, não pela tela.

**6. Meio de pagamento novo é módulo novo, não alteração do núcleo.**

Um segundo agregador, o Pix de um banco específico, um agente TEF local para maquininha
por serial — cada um é um módulo implementando a mesma porta, ativado só para o cliente que
pediu e aceitou pagar pela personalização ou pela taxa de implantação. É o que torna
"atende o pedido específico daquele cliente" sustentável em vez de virar dívida no tronco.

## Consequências

- **Boleto não cabe no enum atual.** `FormaPagamento` tem cinco valores e boleto não é um
  deles. Entra por migração, e a decisão de incluí-lo depende de o agregador escolhido
  tratá-lo — logo, vem depois da escolha, não antes.
- **Pagamento deixa de ser instantâneo.** Pix e boleto confirmam depois, por aviso do
  provedor. Isso traz estado intermediário (`pendente`) e recebimento assíncrono, que o
  modelo atual não tem: hoje pagamento registrado é pagamento feito. É a mudança mais cara
  desta decisão, e ela atinge o fechamento da venda.
- **Entra segredo de terceiro no sistema.** Chave de API de provedor, por empresa. Pela
  regra 3 do `CLAUDE.md` não pode estar em código; por ser por empresa, também não cabe só
  em variável de ambiente. Onde guardar credencial de terceiro por empresa é decisão que
  este ADR **não** toma e que bloqueia a implementação.
- **Conciliação vira requisito.** Saber que entrou não é saber que caiu na conta. É aqui
  que a ADR 0014 (conta de recebimento) encosta nesta decisão.
- **Dependência comercial concentrada.** Um agregador só é também um ponto único de falha
  e de preço. A porta é o que torna a troca possível sem reescrever o PDV — é a mitigação,
  e é deliberada.

## Alternativas consideradas

**Integrar cada meio direto na fonte** (Pix pelo banco, cartão por adquirente, boleto por
outro banco). Dá a melhor taxa e o pior custo de manutenção: são integrações, homologações
e certificações independentes, cada uma com seu ritmo de quebra. Descartada para o tamanho
atual do projeto — uma pessoa.

**Provedor no núcleo, ligado por configuração.** Mais simples de escrever e pior de
sustentar: todo cliente carrega o código de todos os provedores, e cada provedor novo mexe
em código que todo mundo usa. Contraria a ADR 0004 e a razão de o sistema ser modular.

**Adiar e continuar só registrando.** É o estado de hoje, e segue válido enquanto não
houver cliente pedindo. O ADR existe para que, quando houver, a resposta não seja
improvisada dentro do `pdv`.

## Questões em aberto

Nenhuma delas é detalhe de implementação: cada uma muda o que será construído, e o domínio
é regulado demais para supor (regra 6 do `CLAUDE.md`).

1. **Qual agregador.** Decisão comercial, não técnica, e precisa de dados que o projeto
   ainda não tem: taxa por bandeira e por antecipação, prazo de repasse, custo do Pix,
   exigência de certificação, qualidade da documentação e o que acontece com o suporte
   quando o caixa para às 18h de sábado.
2. **Maquininha física ou pagamento no sistema.** Capturar pela API do agregador e capturar
   pela maquininha que já está no balcão são caminhos diferentes, com equipamento
   diferente. O discovery de periféricos no PR #12 levanta isso e não responde.
3. **Onde guardar a credencial do provedor por empresa.** Bloqueia a implementação, como
   dito acima.
4. **Quem concilia.** Se o sistema reconcilia extrato com venda, isso é funcionalidade
   própria, com tela e com custo — não um efeito colateral da integração.
