# ADR 0020 — Operador, supervisor e papéis

**Data:** 10/11/2026
**Estado:** aceita
**Requisito:** `docs/discovery/pdv-operador-supervisor-e-papeis.md`

## Contexto

O modelo de papel e permissão existe desde a primeira migração e é bom: permissão é texto
declarado pelo manifesto do módulo, papel é por empresa, e a trilha de auditoria só aceita
inserção.

O que não existe é **como mexer nisso**. `core.user.create`, `core.user.update`,
`core.user.deactivate`, `core.role.read` e `core.role.assign` estão declaradas no manifesto
do núcleo, chegam no token de quem entra, e **não têm uma única rota por trás**. O único
jeito de criar gente é o `decko-admin bootstrap`, na linha de comando do servidor.

Ou seja: **o dono da loja não consegue criar o operador dele.** Nada do que o dono do
projeto pediu em 10/11/2026 — operador que só vende, supervisor que autoriza, trilha de
quem fez o quê — é alcançável sem isso primeiro.

## Decisões

### 1. O operador tem conta própria; o PIN é atalho, não identidade

No Odoo a sessão do PDV pertence a um usuário e os funcionários se identificam dentro dela,
por crachá ou PIN, contra o cadastro de `hr.employee`. **Divergimos**, e de propósito.

Lá o desenho existe porque o PDV é um cliente offline que troca de funcionário o tempo
todo, e a identidade mora no RH. Aqui a rastreabilidade pesa mais: *"pra não ter caixa 2"*
é o requisito, e ele só se sustenta se **quem assina a venda for quem o token diz**. Com
conta própria, `pdv_venda.operador_id` e `audit_log.user_id` apontam para a mesma pessoa,
sem um campo paralelo que pode divergir.

O PIN entra depois, como **forma rápida de entrar** na estação — não como uma segunda
identidade. O crachá é a mesma coisa por outra entrada: o leitor de código de barras já se
apresenta como teclado (ADR 0008), então o crachá é um código lido num campo.

Quando o módulo de RH existir, o funcionário passa a apontar para este usuário. O lugar
fica reservado agora para o RH não nascer com uma identidade competindo com a primeira.

### 2. O manifesto do módulo declara os papéis que ele sugere

Permissão já é declarada pelo manifesto — *"quem declara as permissões existentes é o
manifesto do módulo, então uma tabela de permissões no banco sairia de sincronia"*. Papel
sugerido segue a mesma regra, no mesmo arquivo:

```toml
[[roles]]
name = "Operador de caixa"
description = "..."
grants = ["pdv.venda.write", "pdv.caixa.abrir", "comercial.produto.read"]
```

A alternativa seria uma lista de papéis na interface ou no núcleo, e aí acrescentar um
módulo exigiria lembrar de editar dois lugares — um deles ficaria para trás. É o mesmo
motivo pelo qual a vitrine do módulo mora no manifesto.

Um papel só pode conceder permissão de módulo que o seu declare em `depends`. O operador
precisa ler produto para vender, e o PDV já depende de `comercial`.

### 3. Papel semeado é ponto de partida, nunca configuração imposta

Os papéis sugeridos são criados **na empresa que não os tem**, e depois disso **nunca mais
são tocados**. É a mesma regra que o reconciliador de permissões já segue — *"papéis que o
cliente tenha criado não são tocados: o que o operador de caixa pode fazer é decisão da
empresa"* — e o princípio da ADR 0010: semente é ponto de partida.

Sem isso, a primeira vez que a loja ajustasse o papel do operador, a subida seguinte da
aplicação desfaria o ajuste, e ninguém entenderia por quê.

### 4. A autorização do supervisor é conferida no servidor, na mesma requisição

Cinco ações passam a exigir credencial de quem pode autorizar: **cancelar item, cancelar
venda, sangria, devolução e desconto acima do limite**, mais o **fechamento com diferença
acima do limite** — esta última é a única que o Odoo tem de fábrica (*Set Maximum
Difference*); as outras cinco, no Odoo, são módulo pago de terceiro.

A regra que sustenta o mecanismo: **a credencial vai junto com a ação, e o servidor confere
antes de executar.** Nunca "destravar a tela". Destravar tela é teatro — quem abre o
inspetor passa por cima, e o controle que existe para impedir fraude seria burlável por
quem tem mais motivo para burlá-lo.

A trilha registra **as duas pessoas**: quem pediu e quem autorizou. Uma linha que diz só
"sangria de R$ 200" não responde nada numa investigação.

### 5. O PDV é a casca do operador, e o menu esconde por permissão

Quem só tem permissão de operar entra direto no PDV, sem menu lateral. Abrir caixa,
sangria, suprimento, fechar contando e devolver são **ações dentro da tela do PDV**, não
telas irmãs dela no menu — que é como estavam, e estava errado.

A conferência do dia continua fora, no menu, porque é do dono: soma o dia inteiro entre
operadores, e é relatório, não operação.

O menu passa a esconder por **permissão**, e não só por módulo ativo.

> **Achado ao percorrer a tela do operador, em 10/11/2026.** A conferência do dia exigia
> `pdv.venda.read` — que o operador **precisa ter para vender**. Ela lhe entregava o
> relatório do dia inteiro, por operador, com o esperado em espécie: o mesmo vazamento que
> a conferência cega da ADR 0008 existe para impedir, entrando por outra porta. Ganhou
> permissão própria, `pdv.caixa.conferir`, que o supervisor tem e o operador não.
>
> Esconder no menu não bastaria, e por isso a permissão é conferida na rota: quem some do
> menu continua alcançando a URL.

### 6. Senha inicial é trocada na primeira entrada

O dono cria o operador com uma senha inicial. O operador **é obrigado a trocá-la** ao
entrar pela primeira vez.

Sem isso a trilha não vale nada: se o dono conhece a senha do operador, "quem fez" é sempre
contestável, e o controle inteiro desta ADR vira enfeite. A troca obrigatória é o que torna
a credencial de alguém, de fato.

## O que fica de fora, de propósito

- **Nível de plataforma** — o dono do Decko enxergando através das empresas. Hoje o
  isolamento é RLS, com dois papéis de banco e nenhum com `BYPASSRLS`, de propósito
  (ADR 0001). Atravessar essa fronteira é decisão própria, com risco próprio, e precisa de
  ADR própria antes de qualquer linha.
- **Criar e editar papel pela interface.** Nesta primeira versão o dono **escolhe** entre
  os papéis semeados; não monta um do zero. É o que o Odoo tem nativamente (dois níveis), e
  é o suficiente para o operador existir. Editar permissão a permissão é o passo seguinte,
  e aí precisa de `core.role.write`, que ainda não está declarada.
- **Aprovação remota pelo chefe.** A entidade de autorização prevê os dois caminhos — PIN na
  hora e pedido liberado à distância — mas o remoto depende de um canal de notificação que
  o projeto não tem: nem push, nem e-mail transacional, nem fila.
- **Biometria (Digital Persona, facial).** O navegador não alcança o leitor, e isso exige
  agente local no Windows — a mesma lacuna que trava TEF e porta serial, que já espera ADR.

## Consequências

- O dono da loja passa a administrar a própria equipe, que é condição para vender o produto
  a quem tem mais de um funcionário.
- Toda operação de caixa passa a ter dono registrado, o que é a regra 2 do `CLAUDE.md`
  valendo no módulo que mais precisa dela.
- O PDV ganha uma fronteira clara entre operação e administração, e a tela do operador
  deixa de oferecer o que ele não pode usar.
- **Risco assumido:** a autorização por credencial batida no balcão convida ao hábito de o
  supervisor entregar o PIN ao operador. O sistema não impede isso — mas a trilha mostra o
  padrão, que é o que permite ao dono perceber.
