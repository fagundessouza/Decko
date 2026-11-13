# ADR 0021 — Nível de plataforma

**Data:** 13/11/2026
**Estado:** aceita
**Requisito:** `docs/discovery/assinaturas-dois-modulos.md`, seção 6

## Contexto

Em 13/11/2026 a primeira empresa cliente entrou na plataforma: **Agrodrone Serviços e
Agronegócios**, com o módulo `agro`. E a pergunta veio na hora:

> *"Se a agrodrone foi criada, como ela não está nem em clientes e nem em assinaturas? Como
> vou ter controle da agrodrone?"*

A resposta é que são duas coisas em lados opostos da fronteira de isolamento, e nada as
ligava:

- `tenant` é tabela **da plataforma**, fora de qualquer empresa. É a própria fronteira.
- `clientes_cliente` e `assinaturas_assinatura` vivem **dentro** da empresa `decko`.
- A assinatura aponta para um contato, nunca para a empresa que usa o sistema.

Até aqui, "quem usa o Decko" e "quem o Decko cobra" eram universos que não se tocavam. O
modelo de negócio exige que se toquem: é assinatura do **próprio sistema**, e bloquear quem
não paga é suspender o acesso de uma empresa.

O isolamento por Row Level Security, com dois papéis de banco e **nenhum com
`BYPASSRLS`**, é a garantia mais forte deste projeto (ADR 0001). Qualquer coisa chamada
"nível de plataforma" nasce sob suspeita de furá-la, e por isso esta ADR existe antes de
uma linha de código.

## Decisões

### 1. Existe um nível de plataforma, e ele é de **pessoa**, não de papel

Administrar a plataforma não é uma permissão de empresa. Se fosse, seria declarada por
manifesto, e o reconciliador a concederia ao papel `Administrador` **de toda empresa** —
inclusive ao da Agrodrone. A conta do cliente ganharia acesso à lista de clientes.

Então o nível é uma marca na pessoa: `user_account.is_platform_admin`, falsa por padrão,
ligada **só pela linha de comando** do servidor — o mesmo lugar de onde empresa nasce.

Nenhum papel concede isso, nenhuma tela dá isso, e a tela de equipe não mostra nem mexe.
Quem administra a própria empresa não encosta nisto.

### 2. A marca é conferida no banco, não no token

Para tudo o mais, a permissão vem do token: é barato e a lista é pequena. Para este nível,
a conferência vai ao banco a cada requisição.

O motivo é o custo do erro: token vive quinze minutos, e tirar a marca de alguém só teria
efeito depois que o dele expirasse. Para privilégio que atravessa empresas, quinze minutos
de atraso é tempo demais.

### 3. A primeira fatia **não atravessa o isolamento**

Listar as empresas lê a tabela `tenant`, que **não tem RLS** — ela é a fronteira, não está
dentro dela. Assinatura, cobrança e contato são lidos como a empresa `decko`, que é o que o
dono do projeto já é. Nada disso é travessia.

O que seria travessia — ler o que cada empresa tem dentro, como os módulos ativos ou o
movimento dela — **fica de fora**. Quando houver motivo, cada leitura dessas é uma decisão
própria, com justificativa própria, e não um portão aberto porque já existe um nível.

### 4. O contato aponta para a empresa, e não o contrário

`clientes_cliente` ganha `tenant_assinante_id`, nulo por padrão: *"este cliente é a empresa
`agrodrone` na plataforma"*.

A alternativa era a assinatura apontar direto para o `tenant`. Foi recusada porque quebra o
outro caso do módulo, que é real: academia cobrando mensalidade de aluno que não usa
sistema nenhum. Com o vínculo no contato, a cobrança continua exatamente como está, e o que
muda é um campo a mais que diz a quem aquele dinheiro dá acesso.

**Uma empresa é apontada por no máximo um contato**, e o banco recusa o segundo: duas
assinaturas pagando o mesmo acesso tornaria "está bloqueada?" uma pergunta sem resposta.

### 5. Cortar o acesso continua sendo outra coisa

Esta ADR liga as pontas e **não corta ninguém**. A seção 5 do discovery já dizia que
bloquear a assinatura marca o estado dela e não corta acesso; agora o estado ao menos sabe
de quem é.

Recusar o login de uma empresa inadimplente é ato do núcleo, na autenticação, e precisa de
respostas que ainda não existem: o que acontece com quem está no meio de uma venda, o que o
bloqueado vê, e como o pagamento devolve o acesso sem alguém passar na mão. Entra quando
essas estiverem escritas.

## O que fica de fora, de propósito

- **Ler dado de dentro das empresas.** Nenhuma consulta de plataforma atravessa RLS nesta
  fatia. Quando precisar, é decisão própria.
- **Criar empresa pela interface.** Continua sendo `decko-admin bootstrap`. Cadastro de
  empresa por auto-serviço é item de MVP do `NEGOCIO.md` e tem exigências próprias.
- **Suspender acesso automaticamente.** Decisão 5.
- **Mais de um administrador de plataforma por engano.** A marca é manual e rara; se um dia
  houver equipe, a lista de quem a tem é consultável pela mesma linha de comando.

## Consequências

- O dono do projeto passa a enxergar quem usa o Decko, e a ligar cada empresa à assinatura
  que a paga. É a condição para cobrar sem planilha paralela.
- O isolamento continua intacto: nada nesta fatia lê de dentro de uma empresa alheia.
- **Risco assumido:** a marca de plataforma é poder concentrado numa pessoa, e ela não tem
  segundo fator. Enquanto for só o dono do projeto, o risco é o da conta dele; quando
  houver equipe de suporte, isto precisa de revisão.
