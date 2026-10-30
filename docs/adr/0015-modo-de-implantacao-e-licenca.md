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

### 2. Hospedado por nós é o padrão; local é exceção

> **Corrigido no mesmo dia, 30/10/2026.** A primeira redação desta decisão dizia "começa
> local". Estava errada, e a objeção do dono do projeto é que a derrubou:
>
> > *"Pensa comigo: eu tendo 50 clientes, ou até uns 100, como vou ir pessoalmente em cada
> > um? Instalação local na máquina do cliente é inviável."*
>
> Está certo. O erro foi otimizar para o custo de hoje e ignorar a armadilha de amanhã:
> começar local e dar certo significa migrar cinquenta instalações à mão.

**Cem clientes não são cem instalações. São cem linhas na tabela `tenant`.**

O Decko é multi-inquilino desde a primeira migração: um processo, um banco, isolamento por
Row Level Security. Cadastrar um cliente é inserir uma linha — não subir container, não
criar banco, não visitar ninguém. A arquitetura escolhida pela ADR 0001 é exatamente o que
torna isto barato, e vale dizer porque de dentro do código não se enxerga.

A conta fecha pelo lado do custo também: **uma visita a um cliente custa mais que um mês de
servidor.** Combustível e meio dia contra algo entre R$ 43 e R$ 60 por mês.

**O que foi medido** nesta máquina de desenvolvimento, em 30/10/2026, para a conversa não
ficar no achismo:

| Medida | Valor |
|---|---|
| Banco com 10 empresas | 17 MB — quase tudo índice e schema, não dado |
| `GET /core/auth/me` | 5,2 ms |
| `GET /comercial/produtos` | 5,0 ms |
| `GET /pdv/vendas` | 15,2 ms |
| `GET /financeiro/contas` | 1,9 ms |

Requisição custa milissegundo de um dígito, e carga de balcão é intermitente: cada caixa
faz uma chamada a cada poucos segundos. Um VPS de 2 a 4 vCPU comporta dezenas de lojas por
esse raciocínio — **e ninguém mediu sob carga real**, que é a lacuna honesta desta decisão.

**Instalação local continua existindo**, para o cliente que exigir o dado na própria casa ou
que opere sem internet confiável. É exceção com preço próprio, porque carrega o custo de
suporte presencial — e é por ela que a licença da decisão 3 existe.

### 2.1 E a máquina de casa?

A pergunta veio com a máquina junto: Ryzen 7 5700, 16 GB de RAM, 700 GB livres. **O
hardware não é o problema** — é quatro vezes o VPS de entrada. A casa é.

**CGNAT.** Internet residencial brasileira raramente dá IP público: a Claro divide um IP
entre 30 e mais de 100 assinantes, e pedir IP fixo no suporte leva ao plano empresarial.
Sem IP público não há porta para abrir. Dá para conferir: se o IP de WAN do roteador estiver
em `100.64.0.0/10`, é CGNAT.

**Disponibilidade.** Falta de luz, queda de internet, Windows Update e um reinicio para
jogar derrubam **todos** os clientes ao mesmo tempo. O requisito escrito pelo dono é que o
sistema "não trave nem dê indícios do cliente reclamar" — e um PC de casa é a fonte mais
provável exatamente disso.

**Dado de terceiro em casa.** CPF e CNPJ de clientes de clientes, na mesma máquina onde se
acessa banco e e-mail pessoal.

**A conta de luz — e a correção.** A primeira versão desta seção calculou 24/7 e concluiu
que custaria R$ 32 a R$ 65 por mês, "o preço do VPS". **Estava errado para o caso real**, e
o dono apontou: a máquina dele já fica ligada manhã, tarde e noite, e desliga para dormir.
O custo **marginal** de hospedar nela é praticamente zero.

A conta de 24/7 fica registrada porque vale para quem ligaria a máquina só para isso — 60 a
90 W dão 43 a 65 kWh por mês, entre R$ 32 e R$ 65 conforme a tarifa. Para quem já deixa
ligado, o argumento não se aplica. **Faltou perguntar o padrão de uso antes de calcular.**

### 2.2 O investimento inicial não existe — é escolha de fornecedor

A objeção seguinte foi de caixa, e é a que realmente decide:

> *"Tenho que pagar o valor cheio, 12 ou 24 meses; estamos falando de mais de mil reais de
> investimento inicial."*

Verdade **para aquele fornecedor**. Hostinger vende VPS com 12 a 24 meses pagos à frente, e
é isso que produz os R$ 1.000 — não o preço do servidor.

**Hetzner, DigitalOcean e Vultr cobram por uso, mês a mês, sem fidelidade.** A máquina de
entrada da Hetzner (2 vCPU, 4 GB) ficou entre € 4,49 e € 5,49 nas fontes consultadas — algo
como R$ 28 a R$ 35 por mês, **sem pagar nada adiantado**. Os preços divergiram entre as
fontes e a Hetzner reajustou duas vezes em 2026: **confirmar na tabela oficial** antes de
decidir.

A conclusão muda o plano inteiro: **não há investimento inicial de mil reais.** Há uma
mensalidade de trinta, que começa quando houver o primeiro cliente e para quando se quiser.

### 2.3 Mikrotik não resolve CGNAT

Perguntado, e vale a resposta: **nenhum roteador resolve.** CGNAT não é limitação do
equipamento da casa — é o provedor não entregando um IP público, porque divide um entre
dezenas de assinantes. Equipamento nenhum cria um IP que não foi dado.

O que resolve é um dos dois: **pedir IP público ao provedor** (quase sempre só no plano
empresarial) ou **túnel reverso** — a máquina de dentro abre a conexão para fora e o
tráfego volta por ela, sem porta aberta e com HTTPS.

**O que a máquina de casa serve, e bem:** desenvolvimento, demonstração e piloto combinado,
com túnel. É o caminho de **custo zero até o primeiro cliente pagante** — e o limite não é
técnico, é do que se promete: máquina que desliga de noite, loja que abre sábado e queda de
luz são aceitáveis num piloto dito como piloto, e não em cliente pagando mensalidade.

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
  com quinze vira refém da estrada. A conta entra no preço de quem pedir instalação local.
- **Observabilidade deixa de ser Fase 7.** O requisito do dono é que o sistema "não trave
  nem dê indícios do cliente reclamar", e isso quer dizer **ver a carga antes de o cliente
  avisar**. Tempo de resposta, taxa de erro e conexões de banco precisam estar visíveis
  antes do décimo cliente, nem que seja do jeito mais simples possível.
- **O pool de conexões vira número a vigiar.** Hoje é `pool_size=10, max_overflow=5` em
  `apps/api/src/decko/db.py`, escolhido quando havia uma empresa. Com dezenas de lojas ele
  é o primeiro limite a aparecer, e aparece como lentidão — exatamente o sintoma que o
  cliente atribui ao software.
- **Backup passa a ser nosso, e isso é vantagem.** Um banco para copiar, com rotina
  testada, em vez de cem computadores de balcão.
- **Hospedagem compartilhada não serve.** Aquele produto é para site e loja em PHP, sem
  processo longo e sem PostgreSQL com papéis próprios e RLS. O certo é **VPS**.
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
