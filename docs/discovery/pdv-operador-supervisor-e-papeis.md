# Discovery — operador, supervisor e papéis no PDV

**Última revisão:** 10/11/2026.

O dono do projeto descreveu, em 10/11/2026, como o controle do caixa precisa funcionar numa
loja de verdade. O pedido não é uma tela: é **quem pode o quê, quem autoriza o quê, e o que
fica registrado**. Este documento separa o que existe, o que o Odoo faz de fato, o que se
deduz das decisões já escritas, e o que continua travado.

## 1. O que foi pedido

Nas palavras dele, resumidas sem perder o que importa:

- O **operador de caixa** é funcionário do dono da loja. A função dele é **vender**. Ele não
  cuida de parte administrativa. Bate a credencial, entra, e enxerga o PDV — só o PDV.
- Ações sensíveis exigem **credencial do supervisor batida na hora**: cancelar produto numa
  venda em andamento, sangria. *"Aquilo tem que ter um log de registro pra evitar fraudes,
  caixa 2 entre outras coisas."*
- Loja pequena não tem supervisor. Então o operador **solicita ao chefe**, e a aprovação
  chega para ele liberar — *"ou quem sabe dispara na conta do chefe pra ele liberar a
  sangria e ficar antenado em tudo que está acontecendo no caixa dele."*
- **Cada operador tem a sua credencial**, e não se mistura com a de outro. Crachá e
  biometria (Digital Persona, facial) entram quando houver.
- **Separar três níveis**: o dono do Decko (ele, que mexe em configuração fina da
  plataforma), o dono da loja (manda na loja dele, não na plataforma) e o operador.
- O menu do PDV está mal orquestrado: *"porque diabos 'meu caixa' está separado do ponto de
  venda"*, e não há como ocultar o que o operador não pode usar.
- Mais à frente, um módulo de **RH** com controle de ponto — registro, digital e facial.
- Regra geral: **fazer o que o Odoo tem, e depois melhorar com o nosso jeito.**

## 2. O que existe hoje — e o buraco que ninguém tinha visto

O modelo de papel e permissão está pronto e é bom: `role`, `role_permission` (permissão como
texto, não chave estrangeira, porque quem declara é o manifesto do módulo), `user_role`, e
uma `audit_log` que só aceita inserção.

**O que não existe é como mexer nisso.** `core.user.create`, `core.user.read`,
`core.role.assign` e `core.role.read` estão declaradas no `modules/core/module.toml`,
aparecem no token de quem entra — e **não têm uma única rota por trás**. Hoje o único jeito
de criar gente é o `decko-admin bootstrap`, na linha de comando da máquina do servidor.

Ou seja: **o dono da loja não consegue criar o operador dele.** Tudo o que foi pedido acima
depende disso primeiro, e o `ROADMAP.md` marca "usuário, papéis, permissões" como feito
porque o **modelo** está feito — a administração não.

Outros três fatos do estado atual:

| Fato | Consequência |
|---|---|
| O PDV **não escreve nada** na `audit_log` | Venda, sangria, devolução e fechamento não deixam rastro de quem fez |
| O menu filtra por **módulo ativo**, não por permissão | O operador vê "Conferência de caixa" mesmo sem poder usá-la |
| Só existe o papel **Administrador**, semeado no bootstrap | Não há "operador" nem "supervisor" para dar a alguém |
| Autenticação é e-mail e senha, com JWT de 15 minutos | Trocar de operador no balcão significa digitar e-mail e senha inteiros |

## 3. O que o Odoo faz de verdade

Confirmado na documentação do Odoo e em material de integradores, porque "o Odoo faz assim"
não pode ser suposição:

- **Login por funcionário no PDV.** O Odoo tem *Log in with Employees*: vários funcionários
  numa mesma sessão de PDV, identificando-se por **crachá** (um `badge ID` lido pelo
  leitor) ou por **PIN** — que é só dígitos. Os dois ficam no cadastro do funcionário, na
  aba de RH. Para trocar de operador com crachá, **tranca-se a sessão** e o próximo passa o
  crachá.
- **A identidade do operador mora no RH**, não no usuário do sistema. É `hr.employee`.
- **Só dois níveis nativos.** Direitos "básicos" e "avançados". Quem tem avançado acessa o
  backend, cria produto e altera preço. Não há, nativamente, permissão separada para
  desconto, devolução ou exclusão de linha — isso é **módulo pago de terceiro**
  (o *POS Access Rights* da DevIntelle acrescenta 16 permissões distintas).
- **Uma única trava nativa de supervisor**, e ela é no fechamento: *Set Maximum Difference*.
  Passando da diferença autorizada, o fechamento trava para usuário não-administrador e um
  gerente precisa aprovar. Sangria e entrada de dinheiro são movimentos registrados, **sem**
  exigência de aprovação nativa; validação por PIN de gerente nessas ações também é módulo
  de terceiro.

**A leitura que importa:** o que ele pediu — credencial de supervisor na hora, por ação,
com log — **é mais do que o Odoo entrega de fábrica**. No Odoo isso se compra. Então "fazer
o que eles têm" aqui significa: login por crachá/PIN, dois níveis, e a trava no fechamento.
O resto é onde o Decko passa na frente, e é defensável fazer: é prática corrente de
supermercado no Brasil, e é exatamente o que evita caixa 2.

## 4. O desenho proposto

### 4.1. Quatro níveis, e só um deles é novo de verdade

| Nível | Quem é | Onde mora |
|---|---|---|
| **Plataforma** | O dono do Decko. Configuração fina, suporte, dados cruzando empresas | **Não existe.** Hoje a empresa `decko` é uma empresa como outra |
| **Dono da loja** | Manda em tudo da empresa dele, inclusive criar gente e papéis | Papel `Administrador`, já semeado |
| **Supervisor** | Vende e **autoriza** o que o operador não pode sozinho | Papel novo, semeado |
| **Operador** | Vende. Abre e fecha o próprio caixa. Mais nada | Papel novo, semeado |

Os três de baixo **não exigem modelo novo**: são papéis com conjuntos de permissão, e o
RBAC já faz isso. O que falta é a administração (seção 2) e os papéis semeados.

O nível de plataforma é outra história e **não entra aqui**: hoje o isolamento é RLS por
empresa, com dois papéis de banco e nenhum com `BYPASSRLS` — de propósito. Um administrador
de plataforma atravessa essa fronteira, e isso precisa de ADR própria antes de uma linha de
código.

### 4.2. A credencial do operador

Proposta, seguindo o Odoo e o que dá para sustentar hoje:

- **PIN numérico por usuário**, guardado com o mesmo algoritmo da senha (nunca em claro).
  É o que permite trocar de operador no balcão sem digitar e-mail e senha.
- **Crachá** é a mesma coisa com outra entrada: o leitor de código de barras **já funciona
  como teclado** (ADR 0008), então o crachá é um código lido no campo — não precisa de
  periférico novo.
- **Biometria (Digital Persona, facial) fica fora por ora**, e pelo motivo já escrito: o
  navegador não alcança o leitor, e isso exige agente local no Windows — a mesma lacuna que
  trava TEF e porta serial, que já espera ADR no `ROADMAP.md`.
- **Quando houver o módulo de RH**, a identidade do operador passa a ser o funcionário, como
  no Odoo. Até lá é o usuário do sistema. Isso precisa ser dito agora para o RH não nascer
  com uma segunda identidade competindo com a primeira.

### 4.3. A autorização no ato

O desenho que vale, e a regra que o sustenta:

**A autorização é conferida no servidor, na mesma requisição que executa a ação.** Nunca
"destrava a tela". Destravar tela é teatro: quem abre o inspetor passa por cima. O operador
manda a ação junto com a credencial do autorizador, e o servidor só executa se aquele
usuário tiver a permissão de autorizar aquilo.

A trilha registra **as duas pessoas**: quem pediu e quem autorizou. Uma linha de auditoria
que diz só "sangria de R$ 200" não serve para nada numa investigação.

Ações candidatas a exigir autorização — a lista é fixa no código, e cada loja liga ou
desliga o que quiser:

- cancelar item de venda em andamento
- cancelar a venda inteira
- desconto acima de um limite
- sangria
- devolução
- fechar caixa com diferença acima de um limite (a única que o Odoo tem nativa)

### 4.4. A aprovação remota, para a loja sem supervisor

A mesma entidade de autorização atende os dois caminhos: **PIN na hora** ou **pedido que o
chefe libera à distância**. A diferença é só como a autorização é satisfeita.

Honestidade sobre o custo: o caminho remoto precisa de um canal de notificação que **não
existe** no projeto — nem push, nem e-mail transacional, nem fila. E precisa que o caixa
fique esperando, o que é decisão de operação, não de código. Proposta: modelar a entidade
agora com os dois caminhos previstos, implementar **só o PIN** primeiro, e deixar o remoto
para quando houver canal.

### 4.5. A trilha

Todo evento de caixa passa a escrever na `audit_log`, que já existe e já é só-inserção:
abrir e fechar caixa, sangria, suprimento, devolução, cancelamento, desconto autorizado.
Com quem fez, quem autorizou, valor e motivo.

Isso não é funcionalidade nova — é a regra 2 do `CLAUDE.md` valendo no módulo que mais
precisa dela.

### 4.6. O PDV como casca do operador

É aqui que o menu se resolve, e a crítica está certa: **"Meu caixa" nunca deveria ser item
de menu irmão do PDV.** No Odoo o PDV é tela cheia, separada do backend, e o caixa do
operador está dentro dela.

Proposta:

- Abrir, lançar sangria e suprimento, fechar contando e devolver passam a ser **ações dentro
  da tela do PDV**, não telas no menu lateral.
- Quem só tem permissão de operar **entra direto no PDV**, sem menu lateral nenhum.
- **"Conferência de caixa" continua no menu**, porque é do dono: ela soma o dia inteiro,
  entre operadores, e é relatório, não operação.
- O menu passa a esconder por **permissão**, e não só por módulo ativo. A tela já recebe
  `info.permissions` e algumas entradas já fazem isso — o PDV não faz.

## 5. Respondido em 10/11/2026

1. **O operador tem conta própria.** O PIN é atalho de entrada dele na estação, não uma
   identidade separada. Consequência: quem assina a venda é quem o token diz, a trilha
   aponta direto para a pessoa, e o módulo de RH depois liga o funcionário a esse usuário —
   sem uma segunda identidade competindo com a primeira. **Divergimos do Odoo aqui**, e de
   propósito: lá a sessão é da máquina porque o PDV é cliente offline que troca de
   funcionário o tempo todo; aqui a rastreabilidade pesa mais.
2. **As quatro ações exigem credencial de supervisor:** cancelar item ou venda, sangria,
   devolução e desconto acima do limite. Mais o fechamento com diferença acima do limite,
   que é o que o Odoo já tem nativo.
3. **Começa pela administração de usuário e papel**, que é o que não existe.

## 6. Situação

| Assunto | Estado |
|---|---|
| Administração de usuário e papel | **Buraco descoberto em 10/11/2026:** permissões declaradas, nenhuma rota. É a primeira fatia |
| Papéis operador e supervisor | **Decidido:** papéis sugeridos pelo manifesto do módulo, semeados por empresa, sem modelo novo |
| Credencial do operador | **Decidido:** conta própria por operador; PIN é atalho de entrada, não identidade |
| Autorização no ato | **Decidido:** quatro ações exigem supervisor, conferido no servidor, com as duas pessoas na trilha |
| Aprovação remota | Proposto: entidade agora, caminho remoto quando houver canal de notificação |
| Trilha no PDV | Proposto: todo evento de caixa escreve |
| PDV como casca do operador | Proposto: caixa e devolução entram na tela do PDV; conferência fica no menu |
| Nível de plataforma | **Fora:** atravessa o isolamento por RLS e precisa de ADR própria |
| Identidade vinda do RH | **Fora:** entra com o módulo de RH, e o desenho já reserva o lugar |
