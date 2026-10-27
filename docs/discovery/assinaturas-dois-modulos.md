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

### Perguntas em aberto

1. O que é vendido por assinatura no seu caso: serviço, entrega recorrente de produto,
   mensalidade de manutenção?
2. A assinatura baixa estoque a cada ciclo (cesta mensal) ou é só cobrança (serviço)?
3. Qual gateway? Pix direto no banco, Asaas, Mercado Pago, Pagar.me?
4. O que acontece quando não paga: suspende, avisa, corta?

---

## 4. Ordem decidida

1. **Clientes** — destrava o plano recorrente e serve ao PDV (venda identificada) e ao
   comprador de licitação.
2. **Assinatura de documento** — o desenho na tela dá para fazer inteiro; a gov.br entra
   quando houver credenciamento.
3. **Plano recorrente** — depois de clientes, e com a resposta sobre gateway.

Regra 6 do `CLAUDE.md` vale para os três: o que não estiver respondido aqui não vira
código.
