# Discovery — "assinaturas" são dois módulos, não um

**Fonte:** Lucas Fagundes Souza, em 25/10/2026, respondendo à pergunta sobre o que o
módulo deveria fazer.
**Status:** requisito colhido, escopo separado. **Nenhum dos dois foi implementado.**

---

## 1. A ambiguidade, e por que ela importava

"Assinatura" em português é duas coisas sem nada em comum:

> *"tenho que ter um módulo pra assinar como se fosse com o dedo ou caneta virtual ou que
> me dê a forma de assinar com a assinatura digital .gov. E quando falo de assinaturas
> também é plano recorrente, então são 2 coisas diferentes."*

Construir um "módulo de assinaturas" sem separar isso daria um módulo que faz metade de
cada coisa. São dois, e as seções abaixo tratam cada um por si.

---

## 2. Módulo A — assinatura de documento

### O que foi pedido

Duas formas de assinar, lado a lado:

1. **Desenho na tela**, com o dedo ou caneta. É o que o cliente faz no balcão ou o
   produtor faz no campo, no celular.
2. **Assinatura digital gov.br**, para quando o documento precisa de peso maior.

### O que a lei separa, e o produto precisa separar junto

A Lei 14.063/2020 reconhece três níveis, e eles **não** valem a mesma coisa:

| Nível | O que é | O desenho na tela |
|---|---|---|
| **Simples** | Identifica o signatário e anexa dados ao documento | É aqui que o desenho cai |
| **Avançada** | Usa certificado não-ICP, com controle exclusivo do signatário | É aqui que a gov.br cai |
| **Qualificada** | Certificado ICP-Brasil | Fora do pedido por ora |

Um rabisco na tela, sozinho, não prova nada. O que o torna defensável é o que vai junto:
**o documento a que ele se prende** (hash do PDF no momento da assinatura), **quem
assinou** (usuário, nome, CPF), **quando** (carimbo de tempo), **de onde** (IP e
dispositivo) e **o fato de nada disso poder ser editado depois**.

O Decko já tem a disciplina para isso — a razão de estoque e a trilha de auditoria são
somente inserção. A assinatura segue o mesmo princípio.

### O que já existe no projeto

O módulo agro tem `agro_signature`: papel, nome, registro profissional e data. É o talão
do MAPA, com quatro assinaturas. **Não guarda o desenho nem prende a assinatura ao
documento** — foi feito para imprimir o PDF, não para valer como prova.

Um módulo de assinatura de documento generaliza isso, e o agro passa a usá-lo.

### O que foi implementado em 27/10/2026 — e onde

**Dentro do módulo agro, não como módulo próprio.** Esta seção propunha um módulo de
assinatura que o agro passaria a usar. Ele não foi feito, e por uma razão escrita no
`CLAUDE.md`: *"Não crie abstração para caso hipotético. A complexidade precisa ser
ganha."* Hoje há **um** consumidor, e ele já tinha a tabela — `agro_signature`, com os
quatro papéis do formulário, criada na primeira migração. Generalizar antes do segundo
consumidor seria inventar uma fronteira para atravessá-la sozinho.

Quando a segunda coisa precisar de assinatura (um cupom de venda, um contrato), o módulo
nasce e o agro migra. Isso está escrito aqui para ser uma decisão, e não um esquecimento.

O que a assinatura guarda, além do traço:

| Guardado | Por quê |
|---|---|
| O desenho, em linhas de pontos de 0 a 1 | Vetor, não imagem: imprime nítido e não leva pixel de celular para dentro do documento |
| `documento_hash` | SHA-256 dos dados do documento **sem as assinaturas** — senão cada uma mudaria o que a seguinte assina |
| Quem operou, quando, de qual IP e aparelho | É o que a Lei 14.063/2020 pede da assinatura eletrônica simples: identificar o signatário e anexar dados ao documento |

**O que isso compra, e é o ponto:** editar o planejamento depois de assinado deixa o hash
de bater, e a tela avisa quem for conferir — antes do fiscal.

Assinar o mesmo papel duas vezes é recusado: trocar assinatura em silêncio, num documento
com efeito legal, é o que ninguém descobre a tempo.

### O que bloqueia

- **gov.br exige credenciamento.** A API de Assinatura Eletrônica do gov.br não é aberta:
  é preciso cadastrar a aplicação, obter client id e secret, e o fluxo é OAuth com
  redirecionamento ao portal. Sem essas credenciais não há o que integrar — e fingir a
  integração seria pior que não ter.
- **Onde guardar o documento assinado.** PDF assinado é arquivo, e o projeto ainda não
  tem armazenamento de arquivo (MinIO está na infraestrutura, mas não em uso).

### Perguntas em aberto

1. O que se assina? Planejamento operacional do agro, cupom de venda, contrato, orçamento?
   A lista muda o módulo.
2. Quem assina é usuário do sistema ou pessoa de fora, por link?
3. O desenho sozinho basta para o uso que você tem em mente, ou a gov.br é obrigatória
   desde o começo?
4. Você já tem conta de desenvolvedor no gov.br, ou isso precisa ser providenciado?

---

## 3. Módulo B — plano recorrente

### O que foi pedido

Cobrança que se repete: o cliente assina um plano e paga todo mês.

### O que ele precisa que ainda não existe

1. **Cadastro de clientes.** Uma assinatura pertence a alguém. É dependência dura, e é o
   motivo de o módulo de clientes vir primeiro.
2. **Meio de pagamento.** Cobrança recorrente de verdade é Pix ou cartão por gateway, o
   que exige conta, credenciais e tratamento de webhook. Sem isso, dá para gerar a
   cobrança e marcar como paga à mão — útil para quem cobra por boleto ou no balcão, e
   honesto sobre o que faz.

### Atualização de 30/10/2026 — o primeiro assinante é a própria Decko

Duas das quatro perguntas abaixo foram respondidas, e o caso de uso ficou concreto: o
produto vendido por assinatura **é o próprio Decko**, e o primeiro a usar o módulo é quem o
escreve.

> *"Eu sou adepto ao use, vista e fale. (…) Preciso ter o controle automático de assinatura
> dos meus clientes, usar meu próprio sistema também."*

| Pergunta | Resposta |
|---|---|
| 1. O que é vendido | **Serviço**: acesso ao próprio Decko, por assinatura fechada |
| 2. Baixa estoque por ciclo? | **Não.** É só cobrança — não há mercadoria saindo |
| 3. Gateway | **Em aberto** |
| 4. O que acontece quando não paga | **Em aberto**, e agora mais pesado: ver abaixo |

**Por que a pergunta 4 ficou mais difícil.** Quando a assinatura é do próprio sistema, "o
que acontece quando não paga" deixa de ser aviso e vira **suspender o acesso de uma
empresa** — ato do núcleo, com efeito sobre gente que está trabalhando. Precisa de resposta
antes do código: avisa e deixa usar, bloqueia telas novas e mantém o que existe, ou corta?
E depois de quantos dias? E quem pode reverter?

**O que dá para construir sem a pergunta 3.** O `ROADMAP.md` já decidiu: plano, assinante,
ciclo e cobrança gerada, marcada como paga à mão. É útil para quem cobra por Pix manual ou
boleto, e honesto sobre o que faz. O gateway entra depois como forma de **confirmar**
pagamento, sem mudar o resto.

### Perguntas em aberto

1. ~~O que é vendido por assinatura~~ — respondido: acesso ao próprio Decko.
2. ~~A assinatura baixa estoque a cada ciclo~~ — respondido: não, é só cobrança.
3. Qual gateway? Pix direto no banco, Asaas, Mercado Pago, Pagar.me?
4. O que acontece quando não paga: avisa, bloqueia o que é novo, ou corta? Em quantos
   dias? Quem reverte?
5. **Qual o plano, e quanto custa?** Não há preço definido em lugar nenhum — ver as
   perguntas em aberto do `docs/NEGOCIO.md`.
6. **A assinatura cobra por empresa, por usuário ou por módulo?** Muda o modelo de dados,
   não só o preço.
7. **Quem emite a nota da mensalidade?** Vender assinatura é prestar serviço, e serviço
   pede **NFS-e**, que é da prefeitura — outro documento, outro caminho, e nenhum dos dois
   é a NFC-e do balcão.

---

## 4. Ordem decidida

1. **Clientes** — destrava o plano recorrente e serve ao PDV (venda identificada) e ao
   comprador de licitação.
2. **Assinatura de documento** — o desenho na tela dá para fazer inteiro; a gov.br entra
   quando houver credenciamento.
3. **Plano recorrente** — depois de clientes, e com a resposta sobre gateway. **Em
   andamento desde 30/10/2026**, com o próprio Decko como primeiro assinante.

Regra 6 do `CLAUDE.md` vale para os três: o que não estiver respondido aqui não vira
código.
