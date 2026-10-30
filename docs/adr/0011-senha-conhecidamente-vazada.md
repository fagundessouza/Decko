# ADR 0011 — Recusar senha conhecidamente vazada

- **Data:** 2026-10-29
- **Status:** aceito

## Contexto

O `ROADMAP.md` trazia a exigência desde a Fase 1, com o motivo junto: *"Vale mais que
exigir comprimento alto, que é o que o mínimo de caracteres tenta aproximar e não
entrega."*

A frase é curta e está certa. Regra de composição — oito caracteres, uma maiúscula, um
número, um símbolo — produz `Senha@123`, que está em toda lista de senha vazada que
existe, e **passa**. O que a regra tenta aproximar é "esta senha é difícil de adivinhar", e
o jeito direto de responder isso é perguntar se ela já apareceu num vazamento.

É também o que a NIST recomenda desde a revisão 3 da SP 800-63B: conferir contra lista de
senhas comprometidas, e **parar** de impor composição e troca periódica, que empurram a
pessoa para padrões previsíveis.

## Decisão

### 1. Conferir no Pwned Passwords, por k-anonimato

O serviço indexa senhas vazadas pelo SHA-1. A consulta manda os **cinco primeiros
caracteres hexadecimais** do hash e recebe de volta todos os sufixos daquele prefixo; a
comparação acontece aqui dentro.

O que sai do Decko é um prefixo compartilhado por dezenas de milhares de senhas. A senha
não sai, o hash inteiro não sai, e o serviço não tem como saber qual delas se conferiu.

Vai junto o cabeçalho `Add-Padding: true`, que faz a resposta vir com preenchimento: sem
ele, **o tamanho** da resposta é uma pista sobre o prefixo consultado.

> **O SHA-1 aqui não é escolha de segurança.** É o formato do índice do serviço. O
> armazenamento da senha no Decko continua sendo Argon2id, e nada neste documento muda
> isso.

### 2. Falha aberta, e dito em voz alta

Serviço fora do ar, rede ruim, tempo esgotado: a senha é **aceita**, e o fato de a
conferência não ter rodado é registrado.

A alternativa é impedir alguém de criar a própria empresa porque um serviço de terceiro
caiu. Entre "pode entrar uma senha fraca" e "ninguém consegue trabalhar", a primeira é a
falha menos grave — e é a única que a pessoa pode corrigir depois.

### 3. Desligável por configuração

`DECKO_BREACH_CHECK_ENABLED=false`. O alvo do produto inclui instalação sem internet, e
numa delas a conferência é latência garantida sem resposta possível. Desligar é decisão de
quem implanta, não defeito.

### 4. Qualquer ocorrência basta para recusar

Uma aparição já significa que a senha está em alguma lista que alguém usa para tentar.
Não há limite mínimo a calibrar.

### 5. Entra onde a senha é definida

Hoje é **um** lugar: o cadastro da empresa, no `decko-admin`. Não existe cadastro de
usuário por rota nem troca de senha — `core.user.create` está no manifesto sem consumidor,
como `core.audit.read` esteve.

O item do roadmap dizia "no cadastro **e na troca**". A troca não existe para ser ligada, e
inventar a rota agora seria fazer o item errado. A conferência fica pronta e isolada; o dia
em que a troca existir, ligá-la é uma linha.

## Consequências

- Uma dependência externa entra no caminho de definir senha. Ela é opcional, tem tempo
  esgotado curto e falha aberta — mas existe, e está registrada aqui por isso.
- O teste não toca a rede: a conferência recebe o cliente HTTP por parâmetro, e a suíte
  passa um que responde o que o teste quiser. Teste que depende de serviço de terceiro
  falha por motivo que não é o código.
- A mensagem de recusa não diz quantas vezes a senha apareceu. O número não ajuda quem vai
  escolher outra, e exibir "apareceu 3.251.237 vezes" é ruído com cara de precisão.

## Alternativas consideradas

**Lista embarcada das senhas mais comuns** — descartada como solução principal. Desatualiza
sozinha, pesa no pacote, e cobre só o topo da distribuição. É o caminho óbvio para a
instalação offline, e fica registrado como possibilidade — mas inventar agora, sem ninguém
operando offline, seria abstração sem consumidor.

**Exigir composição** (maiúscula, número, símbolo) — descartada. É exatamente o que a NIST
desaconselha, e o que produz `Senha@123`.

**Mandar a senha inteira, ou o hash inteiro, para o serviço** — nunca. O k-anonimato existe
para isto não ser necessário.

**Falhar fechado quando o serviço não responde** — descartada pela decisão 2. Transformaria
indisponibilidade de terceiro em indisponibilidade do Decko.
