# ADR 0015 — Modo de implantação e licença

- **Data:** 2026-10-30
- **Status:** aceito
- **Depende de:** ADR 0001 (monólito modular), ADR 0004 (ativação por empresa)
- **Responde:** pergunta aberta 1 do `docs/NEGOCIO.md`

## Contexto

A pergunta chegou com a restrição junto, e é ela que decide:

> *"Investimento com servidores: não consigo deixar online agora, no início, com renda
> zero. A ideia de chegar no ambiente e eu conseguir instalar no ambiente do cliente seria
> muito bom. Agora, problemas que eu encontro: tem alguma maneira de travar ou bloquear
> caso ele não pague?"*

Três coisas se misturam aí e precisam ser separadas antes de decidir: **onde o sistema
roda**, **o que acontece quando não pagam**, e **o que custa de verdade** cada escolha.

## Decisão

### 1. Híbrido, e o código não se divide

O mesmo Decko roda **na casa do cliente** ou **hospedado por nós**. Não há duas versões, não
há ramo separado, não há funcionalidade que só existe de um lado.

O que muda é **onde o processo está e quem opera a máquina**. A arquitetura já comporta os
dois: monólito modular num processo, PostgreSQL, isolamento no banco. Uma instalação local
é o mesmo sistema com **uma empresa só** dentro dele.

O modo é escolhido **por cliente**, e não para sempre. Quem começa local pode migrar: é
dump e restore, porque é o mesmo schema.

### 2. Começa local, por uma razão que não é técnica

Renda zero não paga servidor, e **cliente de balcão não precisa de nuvem**: distribuidora e
padaria operam numa rede local, e um PDV que funciona sem internet é vantagem, não
limitação. A primeira venda não espera infraestrutura.

> **O que precisa estar online primeiro não é o produto do cliente.** É a demonstração e o
> controle de assinaturas — a instância da própria Decko, que tem uma empresa e alguns
> registros. Isso cabe em qualquer lugar barato, e é o único servidor necessário para
> começar a vender.

### 3. A licença expira, e **degrada** em vez de cortar

O bloqueio é uma data de validade conferida na subida e uma vez por dia, com o mesmo
desenho da inadimplência que já foi decidido para assinatura (aviso, prazo, bloqueio):

| Estado | O que acontece |
|---|---|
| Válida | Nada |
| Vencida, dentro do aviso | Avisa na tela, tudo funciona |
| Vencida, passado o prazo | **Operação nova é recusada**: não abre venda, não cadastra |
| Sempre, em qualquer estado | **Ler e exportar os próprios dados continua funcionando** |

**A última linha não é concessão, é limite.** O dado é do cliente — cadastro dele, venda
dele, nota dele —, e a LGPD dá a ele o direito de obtê-lo. Reter dado de cliente como
alavanca de cobrança é problema jurídico e, numa cidade pequena, é problema de reputação
que não se desfaz.

### 4. A licença é dissuasão, não proteção — e isso é assumido

Instalação local quer dizer que o cliente tem a máquina, o banco e o processo. **Qualquer
trava é derrotável** por quem tiver conhecimento: mudar o relógio, editar o banco, alterar o
binário.

Escrito aqui para não se gastar engenharia perseguindo o impossível. O que protege de
verdade é o **contrato**, e o que basta na prática é a trava ser mais trabalhosa que pagar
— para o público-alvo, que é dono de loja, não engenheiro reverso.

Decorre disso: **nada de ofuscação, nada de anti-debug, nada de relógio escondido**. Custa
caro, não resolve, e transforma defeito em suspeita de sabotagem.

### 5. Falha **aberta**, como a conferência de senha vazada

Licença que não pôde ser verificada — sem internet, servidor fora do ar — **deixa o sistema
funcionando**, e registra. O mesmo princípio da ADR 0011: entre "pode escapar um mês não
pago" e "o caixa do cliente parou porque a minha máquina caiu", a segunda é a falha pior, e
é a que destrói a relação.

A validade mora no arquivo de licença, não numa chamada de rede: o sistema precisa
funcionar dias sem internet.

### 6. O frontend vai para a borda; o backend, não

`apps/web` é build estático do Vite e roda bem em Vercel ou Cloudflare Pages, de graça.

O backend **não**. Não por capricho: em serverless o pool de conexões morre com a função e
a plataforma cria processos independentes, então um pooler externo deixa de ser otimização
e vira obrigatório — a própria Neon recomenda PgBouncer em modo transação para tráfego de
aplicação, com conexão direta só para migração.

> **Uma sorte do desenho que vale registrar:** o isolamento do Decko usa
> `set_config('decko.tenant_id', ..., true)`, que é **escopo de transação**, e
> `get_session` sempre abre transação. Isso o torna compatível com pooler em modo
> transação. Se o isolamento fosse por sessão, não seria — e descobriríamos em produção.

Contra o serverless pesa ainda o carregador de módulos, que importa todos os pacotes na
subida: em função sem estado isso acontece a cada partida fria, e **leveza é requisito** do
projeto (regra 5 do `CLAUDE.md`).

O backend quer uma máquina comum com container: a mesma coisa que roda na casa do cliente.

## Consequências

- **O custo escondido da instalação local não é o servidor, é a pessoa.** Instalar,
  atualizar, fazer backup e atender presencialmente. Com três clientes é administrável;
  com quinze vira refém da estrada, e é essa a razão de o SaaS existir. A conta precisa
  entrar no preço desde o primeiro contrato.
- **Backup na casa do cliente é responsabilidade que alguém vai cobrar.** Se o computador
  do balcão queimar com os dados dentro, a culpa chega ao fornecedor, tenha ou não contrato
  dizendo o contrário. Precisa de resposta antes do primeiro cliente — nem que seja cópia
  para pendrive, com instrução escrita.
- A licença precisa de um módulo pequeno e de um jeito de gerar o arquivo assinado. Nada
  disso existe hoje.
- O modo híbrido impede uma classe de atalho: funcionalidade que dependa de serviço nosso
  em tempo real deixa de funcionar na instalação local. Integração de pagamento e Pix,
  quando vierem, nascem com esse limite em mente.

## Alternativas consideradas

**Só SaaS, desde o começo** — descartado pela restrição que originou a pergunta: não há
dinheiro para servidor, e esperar para vender é pior que vender instalando.

**Só instalação local, para sempre** — descartado. Não escala em suporte, e o controle de
assinatura do próprio negócio precisa estar em algum lugar que não seja a casa de um
cliente.

**Backend na Vercel** — descartado pela decisão 6. O frontend sim, e de graça.

**Trava forte: ofuscação, anti-debug, verificação online obrigatória** — descartado pelas
decisões 4 e 5. Custa caro, não resolve contra quem sabe, e a verificação online
obrigatória transforma a minha indisponibilidade na parada do caixa do cliente.

**Bloquear tudo, inclusive leitura, quando não paga** — descartado pela decisão 3. O dado é
do cliente.
