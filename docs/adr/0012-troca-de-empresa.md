# ADR 0012 — Troca de empresa

- **Data:** 2026-10-29
- **Status:** aceito
- **Depende de:** ADR 0001 (isolamento por Row Level Security)

## Contexto

O `ROADMAP.md` pedia "troca de empresa para quem opera em mais de uma" desde a Fase 1. O
caso é real: contador que atende duas lojas, dono de mercado que abriu a lanchonete ao
lado, pessoa que trabalha em duas empresas que usam o Decko.

O modelo já previa a situação, e está escrito no `user_account` desde a primeira migração:

> *"E-mail é único dentro da empresa, não globalmente: a mesma pessoa pode operar em duas
> empresas diferentes com o mesmo endereço."*

São, portanto, **duas contas**, com papéis próprios e **hashes de senha independentes**.
Hoje a única forma de ir de uma para a outra é sair e entrar de novo.

## Decisão

### 1. Não existe rota "liste as minhas empresas"

É a decisão central, e ela é uma recusa.

Responder *"em quais empresas este e-mail tem conta?"* exige consultar `user_account`
atravessando empresas. A tabela está sob Row Level Security, e a consulta só é possível
com privilégio que ignore a política — um furo na parede que sustenta o produto inteiro,
aberto para uma conveniência de tela.

E o resultado seria um **oráculo de enumeração**: uma rota que, dado um endereço,
responde em que empresas aquela pessoa trabalha. Isso não é informação do Decko para dar.

### 2. A lista é do aparelho, não do servidor

As empresas que aparecem no seletor são as que **já entraram neste navegador**, guardadas
em `localStorage` — do mesmo jeito que o código da empresa já é guardado hoje, pela mesma
razão de sempre: o operador digita o mesmo código todo dia.

Isso é honesto sobre o que a lista é. Ela não é "as suas empresas"; é "as empresas usadas
neste aparelho". Num computador compartilhado de balcão, as duas coisas são diferentes, e
quem olha a tela entende a diferença sem precisar que lhe expliquem.

### 3. Trocar pede a senha

As contas são independentes, e os hashes também. Aceitar a sessão da empresa A como prova
para entrar na B faria o token de uma valer na outra — exatamente a travessia que o
isolamento existe para impedir. O RLS protege as linhas; de nada adianta se a porta da
frente aceitar credencial de outra casa.

Então trocar de empresa **é entrar**: mesma rota de login, mesma conferência, mesma trilha.
O que a tela poupa é digitar o código e o e-mail de novo, e perder o contexto.

### 4. A sessão anterior é encerrada antes

A troca revoga o refresh token da empresa de origem antes de pedir o novo. Sem isso,
ficaria um token vivo e sem dono na tela — e o `localStorage` guarda um por vez, de modo
que ele não seria nem revogável depois.

## Consequências

- A trilha da empresa de destino registra `auth.login`, com hora e IP, e a de origem
  registra `auth.logout`. A troca aparece dos dois lados, como de fato aconteceu.
- Quem opera em duas empresas digita a senha a cada troca. É atrito consciente, e o preço
  de o token de uma empresa não valer na outra.
- O servidor não ganhou rota nenhuma nesta decisão. O que faltava era tela, e o motivo de
  não ser mais que tela é a decisão 1.

## Alternativas consideradas

**Identidade única acima das empresas** — uma tabela de pessoa com N contas, uma senha só,
troca sem reautenticar. É o modelo do Slack e é o que a maioria espera. Descartado **por
ora**, e não por ser ruim: muda o núcleo da identidade, exige migração dos cadastros
existentes, e carrega uma decisão de produto que ninguém tomou — se a mesma senha deve
valer em empresas que não têm relação entre si, e o que acontece quando uma delas exige
troca de senha e a outra não. Fica registrado como o caminho, se o requisito aparecer.

**Função `SECURITY DEFINER` para listar as empresas do e-mail** — descartada pela
decisão 1. Resolve a consulta e abre o oráculo.

**Trocar sem senha, confiando na sessão atual** — descartada pela decisão 3. É a
vulnerabilidade que o isolamento existe para não ter.

**Guardar a lista de empresas no servidor, por usuário** — descartada. Seria a mesma
informação da decisão 1 com outro nome, só que persistida: a linha diria que este e-mail
tem conta naquela empresa, legível por quem alcançasse o registro de qualquer uma delas.
