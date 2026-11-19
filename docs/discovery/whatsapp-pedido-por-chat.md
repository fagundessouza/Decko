# Discovery — o pedido entra pelo WhatsApp

**Origem:** pedido do dono do projeto em 19/11/2026, com uma proposta de arquitetura
escrita por ele (catálogo nativo + agente conversacional com guardrails).
**Estado:** apuração técnica, não decisão. Nada foi construído.

> *"vai ter o módulo igual o anota.ai só que melhor: em vez de ficar clicando em links e
> sendo redirecionado, tem que integrar certinho com o catálogo do WhatsApp — quando o
> cliente comprar lá já gerar certinho o orçamento no Decko e realizar a venda, baixa de
> estoque e tudo certinho."*

A pergunta que ele fez, e que este documento responde: **dá para fazer isso na arquitetura
atual, e o que pode sair diferente do que ele está pensando.**

---

## 1. Veredito curto

**A arquitetura proposta está certa.** Os dois caminhos — carrinho nativo do WhatsApp e
agente conversacional — convergindo num serviço único de pedido é o desenho correto, e os
guardrails que ele descreveu (o agente nunca calcula preço, a função determinística
calcula) são exatamente a separação que evita prejuízo.

**O que ele subestimou não é a IA. É a infraestrutura embaixo dela.** Metade das peças que
a proposta assume como existentes **não existem no Decko hoje**, e duas travas que ele não
listou são mais caras do que todas as que ele listou.

---

## 2. O que existe hoje, conferido no código

| Peça que a proposta assume | Estado real |
|---|---|
| FastAPI multi-tenant com isolamento | **Existe.** RLS no PostgreSQL por `decko.tenant_id` |
| Catálogo de produtos por empresa | **Existe.** `comercial`: produto, preço, estoque como razão |
| Baixa de estoque transacional | **Existe.** `comercial.registrar_movimento`, usado pelo PDV e pelo agro |
| Venda com itens e pagamento | **Existe.** `pdv`: venda, item, pagamento, caixa |
| Fila assíncrona (Redis / Arq) | **Não existe.** `apps/worker/` é uma pasta vazia; `redis` não aparece em nenhum arquivo do projeto |
| Tempo real para a cozinha (SSE/WebSocket) | **Não existe.** Nenhuma rota de evento, nenhum consumidor no front |
| Entidade de pedido com ciclo de vida | **Não existe.** A venda do PDV nasce e morre no balcão: não tem "aceito", "em preparo", "saiu para entrega" |
| Guarda de segredo de terceiro no banco | **Não existe.** Não há utilitário de criptografia em repouso; hoje segredo só vem de variável de ambiente |
| Módulo de restaurante | **Não existe.** `docs/discovery/restaurante-pedido-na-cozinha.md` tem oito perguntas em aberto, e a decisiva — como o cliente sabe que ficou pronto — não foi respondida |

Ou seja: o pedido entra, mas **não há onde ele morar** nem **por onde ele avisar**.

---

## 3. As travas que a proposta mapeou, e o que falta em cada uma

As cinco que ele listou estão corretas. Abaixo, só o que acrescenta.

### A. Debounce das mensagens picadas — **correto, e incompleto**

Agrupar por 3 a 5 segundos resolve o atropelo. Falta a outra metade: **a Meta reentrega o
mesmo webhook** quando não recebe 200 a tempo. Sem deduplicar por `message.id`, o cliente
que mandou "e uma coca" uma vez pede duas.

O projeto já resolve esse problema em outro lugar e do mesmo jeito: identidade na origem,
com reenvio reconhecido em vez de duplicado — é o que a venda sem rede faz
(`docs/adr/0022-offline-first-as-respostas.md`). A mesma regra vale aqui.

### B. API oficial vs. não oficial — **a conclusão dele está certa, o risco é maior**

Biblioteca não oficial não é só "instável a cada atualização": ela **viola os termos de uso
do WhatsApp**, e a punição recai sobre o número do lojista. O número é o ativo comercial da
lanchonete — perder o número é perder a clientela, não o software.

Vender um módulo que roda sobre isso é vender um risco que não é nosso e que o cliente não
tem como avaliar. **Recomendação: só API oficial.** O fallback para quem não quiser pagar a
Meta não é a via não oficial — é não ter o módulo.

### C. Impressão térmica — **correto, e com um custo de produto que a proposta não cobra**

A solução (agente local em segundo plano, convertendo para ESC/POS) é a única que funciona.
Mas ela cria o que o Decko não tem hoje: **um executável para instalar, atualizar e
suportar em Windows de lanchonete**.

Isso contradiz uma das promessas atuais do produto — "abre no navegador, sem instalar nada
em cada máquina". Não invalida a ideia; muda o que se promete e o que se cobra.

### D. Alucinação de preço — **a defesa está certa, o risco está no outro lado**

O agente não calcular nada e só extrair itens é a defesa certa. Mas o carrinho nativo, que
a proposta trata como "zero chance de alucinação de preço", tem um risco próprio e maior:

**o preço que o cliente viu é o do catálogo da Meta, não o do Decko.** São duas bases
diferentes, e o espelho atrasa. Se o lojista subiu o preço no Decko e o catálogo da Meta
ainda está com o antigo, o cliente comprou pelo antigo.

E aqui não é questão de preferência: no Brasil a **oferta vincula o fornecedor** (Código de
Defesa do Consumidor, arts. 30 e 35). Preço anunciado é preço devido. Então sincronizar o
catálogo não é tarefa de rotina — é a diferença entre vender e dever.

**Decisão que o dono do projeto precisa tomar:** o pedido que chega com preço divergente é
aceito pelo preço anunciado (e o lojista é avisado) ou é recusado? A primeira opção é a
legalmente segura; a segunda vai gerar briga no chat.

### E. Recurso no servidor — **correto, e não é o gargalo principal**

Delegar IA e transcrição para API externa está certo: o servidor atual tem 1,7 GB de RAM.
Mas o gargalo real não é a inferência (que sai da máquina) — é a **disponibilidade**, na
trava F abaixo.

---

## 4. As duas travas que a proposta não listou — e que decidem o módulo

### F. O servidor de hoje não aguenta ser dono do WhatsApp de ninguém

O Decko em produção roda numa caixinha, na casa do dono do projeto, atrás de um túnel. Isso
funciona para o cliente atual: se cair por vinte minutos de madrugada, o piloto sincroniza
depois — **porque o sistema foi feito para operar sem rede**.

Um módulo de pedidos pelo WhatsApp inverte isso. Ele é **o oposto do offline-first**: se o
servidor não responder ao webhook da Meta, o pedido do cliente final não chega, e ninguém
tem como "sincronizar depois" uma fome de sexta à noite. A indisponibilidade deixa de ser
um incômodo interno e vira **pedido perdido na casa do cliente do cliente**.

Isto é o que muda de patamar: queda de energia no bairro, operadora oscilando, ou o túnel
caindo deixam de ser problema de um usuário e passam a ser problema de todos os clientes
finais de todos os lojistas, ao mesmo tempo, no pior horário.

**Consequência:** este módulo exige hospedagem com responsabilidade de disponibilidade —
servidor gerenciado, não caixinha doméstica. É um custo fixo novo no `NEGOCIO.md`, e ele
precisa caber no preço da assinatura antes de a primeira lanchonete entrar.

### G. Dado pessoal de quem não é cliente do Decko

O módulo passa a guardar telefone, endereço, histórico de conversa e **áudio** de pessoas
que nunca contrataram nada da Decko — são clientes do lojista.

Três consequências concretas:

1. **O áudio vai para fora.** Transcrição em API externa é transferência de dado pessoal
   para outro país, com endereço e nome dentro. Precisa de base legal, contrato com o
   fornecedor e aviso ao titular.
2. **O papel de cada um muda.** O lojista é o controlador; a Decko vira operadora. Isso
   precisa estar escrito no contrato de assinatura, e hoje não está.
3. **O token do WhatsApp do lojista fica no nosso banco.** É segredo de terceiro guardado
   por nós, e o projeto não tem criptografia em repouso — a regra 3 do `CLAUDE.md` diz que
   segredo só vem de variável de ambiente, e isto não cabe lá: é um segredo **por empresa**.

Nenhuma das três impede o módulo. As três precisam de decisão antes da primeira linha de
código, porque mudam contrato, infraestrutura e modelo de dados.

---

## 5. O que precisa existir antes, na ordem

Cada item vale sozinho e serve a mais coisas do que este módulo:

1. **Fila assíncrona de verdade** (`apps/worker` + Redis). Hoje é pasta vazia. Sem ela, o
   webhook responde depois da IA pensar — e a Meta reentrega.
2. **Entidade de pedido com ciclo de vida**, separada da venda do balcão: recebido, aceito,
   em preparo, pronto, saiu, entregue, cancelado. A venda do PDV continua sendo o que ela
   é; o pedido é outro bicho, e vira venda quando fecha.
3. **Canal de tempo real** (SSE basta; WebSocket é mais do que o caso pede) para o painel
   da cozinha receber sem F5.
4. **Guarda de segredo por empresa**, cifrado em repouso, com a chave em variável de
   ambiente.
5. **Espelho de catálogo** com sincronização e marcação de divergência — o item que a trava
   D transforma em risco jurídico.

Só depois disso o adaptador do WhatsApp (webhook, roteador de intenção, agente com tools)
vira trabalho de aplicação, e não de fundação.

---

## 6. Como validar antes de construir o módulo inteiro

A proposta já traz três passos, e eles estão certos. Acrescento o que falta medir:

1. **PoC do fluxo de dados.** Número de teste da API oficial apontando para um endpoint do
   FastAPI, recebendo `order` e `text`, sem IA no caminho.
2. **Debounce e deduplicação.** Mandar cinco mensagens picadas e reenviar o mesmo
   `message.id`: o resultado tem de ser um pedido, uma vez.
3. **Print agent.** Do evento até a comanda saindo da impressora, cronometrado.
4. **Medir o custo por pedido** — e esta é a que decide o preço do módulo. Desde
   **1º de outubro de 2026** a Meta cobra por mensagem, inclusive resposta de atendimento
   dentro da janela de 24 horas, com uma franquia mensal por número. Três avisos de status
   por pedido, em trezentos pedidos no mês, são novecentas mensagens. **Conferir a tabela
   atual na página oficial da Meta antes de prometer qualquer preço** — as fontes
   secundárias divergem entre si.
5. **Medir o pico.** Sexta à noite, com o servidor atual, medindo memória e tempo de
   resposta do webhook. É o número que diz se a trava F é teórica ou imediata.

---

## 7. Perguntas para o dono do projeto

1. **Preço divergente entre o catálogo da Meta e o Decko:** aceita pelo preço anunciado ou
   recusa? (Trava D — e a lei puxa para a primeira.)
2. **Hospedagem:** o módulo só é vendido com servidor gerenciado? Qual custo fixo entra no
   preço da assinatura? (Trava F.)
3. **Quem é o lojista-piloto?** O restaurante da conversa de 04/11 ainda não foi entrevistado,
   e as oito perguntas daquele discovery continuam abertas — inclusive a que decide tudo:
   como o cliente sabe que o pedido ficou pronto.
4. **Transcrição de áudio no primeiro corte, ou texto e catálogo só?** Tirar o áudio da
   primeira versão remove a trava G.1 inteira e metade do custo de IA.
5. **O agente responde sozinho ou sugere e o lojista confirma?** Em sexta à noite, a
   segunda opção é mais lenta e muito mais segura para a marca.

---

## 8. O que isso tem de diferencial, se for feito

Registrado porque é o que justifica o custo acima — e porque o texto da página pública vai
precisar disso quando o módulo existir:

- **O concorrente conhecido manda link e tira o cliente do chat.** Aqui o pedido nasce
  dentro da conversa e já chega como comanda, com baixa de estoque na mesma transação.
- **Catálogo nativo e conversa livre no mesmo lugar.** Quem gosta de clicar, clica; quem
  manda áudio, manda áudio. Os dois caem no mesmo serviço.
- **A conta é do servidor, nunca do modelo.** O agente extrai item; preço, adicional e taxa
  saem de função determinística. É o mesmo princípio da venda sem rede: a máquina não
  inventa número que vira dinheiro.

**Nada disso entra no site antes de existir.** Vender módulo inexistente queima a marca mais
rápido do que qualquer demonstração que der errado.
