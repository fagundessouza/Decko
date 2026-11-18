# ADR 0022 — Offline-first: as respostas que faltavam

**Data:** 17/11/2026
**Estado:** **aceita**, com a resposta 6 decidida de outra forma. As fatias 1 a 4 foram
pedidas uma a uma pelo dono do projeto em 17/11/2026 e estão feitas; a resposta 6, sobre
entrar sem rede, foi decidida por ele no mesmo dia e **não** é o que esta ADR propunha —
ver abaixo.
**Responde:** as questões em aberto da `docs/adr/0019-offline-first.md`
**Depende de:** ADR 0019 (direção), ADR 0008 (ponto de venda), ADR 0020 (operador e papéis)

## Por que esta ADR existe

A ADR 0019 decidiu a direção e **se bloqueou de propósito**: seis questões em aberto, uma
delas já respondida em 04/11. Enquanto elas não tiverem resposta escrita, sincronizar é
inventar regra de negócio, e o `CLAUDE.md` proíbe.

Em 17/11/2026 o dono do projeto reafirmou o escopo, depois de ver a tela abrir sem rede e
não deixar fazer nada:

> *"O lance do offline-first não é só abrir, é continuar fazendo a operação: entrar,
> cadastrando clientes, operando PDV, ou até mesmo sobre a questão da pulverização. Tem
> que manter a operação, não pode morrer ou travar ou parar."*

Esta ADR propõe as respostas. Cada uma vem com o motivo e com o que ela custa, porque
nenhuma é de graça.

## O princípio que organiza todas as respostas

Ele já foi escolhido, na questão 2 da ADR 0019, sobre estoque negativo:

> *"Se não bater a conta é aí que tá o pulo do gato que o dono quer, manter o controle do
> estoque. (…) Se houver, ele já sabe que teve algum problema no dia."*

**A divergência é o produto, não o defeito.** O sistema registra o que aconteceu de
verdade e **mostra** onde as versões discordam; ele não escolhe sozinho uma verdade
confortável nem recusa o que já aconteceu no mundo.

As cinco respostas abaixo são a mesma frase aplicada a casos diferentes.

## As respostas propostas

### 1. Conflito: o tipo da entidade decide, e divergência aparece

| Tipo | Exemplos | Regra |
|---|---|---|
| **Acontecimento** | venda, movimento de estoque, lançamento de pulverização, trilha | Não conflita. Dois aparelhos registram dois fatos distintos, e os dois valem. |
| **Cadastro** | cliente, produto, piloto, dados da empresa | Conflita. Mescla por **campo**, não por registro. |

Na mescla por campo: o aparelho manda o valor novo **e o valor que ele tinha como base**.
Campo que ninguém mais mexeu entra. Campo que mudou dos dois lados **fica com o do
servidor** e gera uma divergência visível, com os dois valores e quem escreveu cada um.

O motivo de não ser "o último ganha": num cadastro fiscal, perder em silêncio o CNPJ que
alguém corrigiu é pior do que mostrar duas versões e pedir um clique.

O motivo de ser por campo: duas pessoas editando o mesmo cliente quase nunca editam o
mesmo campo — uma corrige o telefone, a outra o endereço. Por registro, uma das duas
perderia o trabalho sem motivo.

### 2. Idade: nada é recusado por ser velho; acima de 7 dias entra conferido

O aparelho **nunca** descarta o que está na fila, e o servidor **nunca** recusa por idade.
Recusar uma venda de uma semana atrás apaga o registro de algo que aconteceu — exatamente
o que o controle de estoque existe para impedir.

O que muda com o tempo é a atenção: acima de **7 dias**, o item entra marcado para
conferência e aparece numa lista de pendências, em vez de entrar calado.

### 3. O que fica no aparelho: o que a operação usa, não o catálogo inteiro

- **Sempre:** a empresa, os papéis, os operadores do aparelho, as formas de pagamento, a
  configuração do caixa.
- **PDV:** os produtos **vendidos nos últimos 90 dias** mais os marcados como favoritos.
  Numa distribuidora com dezenas de milhares de itens, o catálogo inteiro não cabe num
  celular fraco — e o item que nunca vendeu também não vai ser vendido offline.
- **Agro:** os planejamentos abertos, os pilotos, os produtos do receituário em uso.
- **Nunca:** consolidação, relatório, trilha, assinaturas. Tudo isso é leitura de
  escritório, e escritório tem rede.

Produto fora do recorte, offline, pode ser vendido **pelo código digitado**, com descrição
pendente de sincronização — não vender o que está na prateleira é pior do que vender com o
nome em branco por algumas horas.

### 4. Permissão revogada com o aparelho fora: aceita o que passou, barra o que vem

Duas perguntas diferentes foram tratadas como uma:

- **O que ela fez às 11h, antes de o aparelho saber:** entra. Aconteceu, e há mercadoria
  saindo ou lavoura pulverizada do outro lado. Entra marcado, na mesma lista de
  conferência da resposta 2.
- **O que ela tenta fazer depois de o aparelho sincronizar:** barrado. A sincronização traz
  a lista de quem pode operar, e o aparelho obedece a ela.

### 5. Quais telas: três, e o resto continua exigindo rede

**Entram:** ponto de venda (venda, caixa, devolução), clientes (criar e editar),
pulverização (planejamento e lançamento de campo).

**Ficam de fora:** consolidação mensal, trilha de auditoria, assinaturas, equipe e papéis,
dados da empresa, entrada por nota. Nenhuma delas acontece longe de rede, e cada uma que
entra custa peso de pacote — que é requisito pela regra 5 do `CLAUDE.md`.

### 6. Entrar sem rede — a pergunta nova, e a mais delicada

Era a parte que faltava para "não pode travar": de nada adianta a venda ficar na fila se o
operador não consegue nem entrar depois que o navegador fechou.

**O que esta ADR propunha:** o aparelho guardaria os operadores que já entraram nele, cada
um com o hash Argon2id do **PIN**, e o PIN abriria uma sessão local — com três limites: só
PIN e nunca senha, validade de 7 dias sem sincronizar, e só em aparelho confiado.

**O que o dono do projeto decidiu, em 17/11/2026** — e vale sobre a proposta:

> *"Sessão persistida com token local/TTL vence a necessidade de complicar com hash de PIN
> no disco."*

Então **não há PIN nesta porta**. O que abre o Decko sem rede é a **sessão que já estava
aberta**: a credencial é o mesmo token de renovação que já reabre a sessão sozinho quando
há rede — recarregar a página online nunca pediu senha de novo. O aparelho guarda, a cada
sessão que o servidor confirma, uma cópia de quem entrou, com as permissões e os módulos
daquele momento, e um prazo.

Três coisas definem o alcance disso:

1. **Validade de 30 dias sem sincronizar**, decisão do dono do projeto, contra os 7 da
   proposta. O prazo é o da operação: a pulverização de uma safra passa semanas longe de
   sinal. Ele conta da **última** confirmação do servidor, então quem passa na sede toda
   semana nunca vê a sessão vencer.
2. **Sem a credencial, a cópia não vale nada.** Quem saiu não entra: sair revoga o token e
   apaga a cópia.
3. **Revogação não é conferida sem rede.** É a resposta 4 valendo aqui: aceita o que já
   estava valendo, e o servidor manda de volta na primeira sincronização — se ele recusar a
   sessão, a tela de entrada volta na hora.

**O que isso custa, dito claramente:** nome, e-mail, papéis e permissões de quem entrou
ficam no disco do aparelho por até 30 dias, ao lado do cadastro de clientes que a fatia 2
já guarda — tudo fora do PostgreSQL e portanto fora do Row Level Security. E, sem o PIN da
proposta, **quem estiver com o tablet alcança a operação sem digitar nada** durante esse
prazo. Isso tem consequência de LGPD: aparelho perdido é incidente a tratar, não
contratempo. O armazenamento local é apagado na saída, com uma exceção deliberada — a fila
de sincronização fica, porque ela não é cópia, é venda que aconteceu e ainda não subiu.
Encurtar a validade é mexer num número só, em `apps/web/src/lib/sessaoGuardada.ts`.

## A pergunta que esta ADR **não** responde

**Como liberar supervisor sem rede.** A credencial de quem libera é conferida no servidor,
na mesma requisição que executa a ação — ADR 0020, decisão 4. Sem rede não há a quem pedir,
e conferir no aparelho seria teatro: quem abre o inspetor passa por cima.

O que está implementado é um remendo, e ele está aqui escrito para não passar por decisão:
o aparelho guarda a configuração da loja na última sincronização e, sem rede, **permite o
que a loja não exige supervisor para fazer** e recusa o resto, dizendo o motivo. Sem
configuração guardada, recusa — supor "pode" seria inventar permissão.

Isso deixa dois casos ruins, e os dois são do dono do projeto decidir:

1. Loja que exige supervisor para retirar item fica sem corrigir um item bipado errado
   enquanto não houver rede. O jeito é cancelar a venda inteira, se isso for livre.
2. Um PIN de supervisor guardado no aparelho resolveria — e seria a fatia 5 valendo também
   para liberação, com o mesmo custo de LGPD dela.

## O que isto não resolve

- **Número de venda e número fiscal** continuam como a ADR 0019 e a 0018 descrevem: o
  `numero` já é nulo até finalizar, e a numeração fiscal segue o regime de contingência.
- **Dois caixas offline podem vender o mesmo último item.** Decidido em 04/11: o saldo
  fica negativo e isso aparece. Esta ADR só acrescenta que a divergência precisa ter
  endereço — qual venda, qual aparelho, quanto faltou.

## Por onde começar, se as respostas forem aceitas

Em fatias que valem sozinhas, na ordem:

1. **Identidade na origem e rotas idempotentes.** ✅ feita em 17/11/2026. O `id` vem do
   aparelho e reenviar o mesmo pacote devolve o que já existe. Não mudou nada visível, e é
   a base de todo o resto.
2. **Fila local e cadastro de cliente offline.** ✅ feita em 17/11/2026. A fila mais
   simples, na tela mais simples — e o que não subiu fica à vista, item por item.
3. **Leitura guardada para o PDV**, pelo recorte da resposta 3. ✅ feita em 17/11/2026,
   decidida no servidor (`pdv.catalogo_do_aparelho`). A metade do agro continua aberta.
4. **Venda offline**, com a divergência de estoque aparecendo na sincronização. ✅ feita em
   17/11/2026, nas duas metades: o servidor recebe a venda que aconteceu
   (`POST /pdv/vendas/do-aparelho`) e o aparelho compõe a venda (`apps/web/src/lib/balcao.ts`).

   Três coisas valem registrar, porque nenhuma delas era óbvia:

   - **A conta de dinheiro desceu para o aparelho**, e isso é uma divergência deliberada da
     decisão 3 da ADR 0008 ("a tela não soma dinheiro"). Sem rede não há a quem perguntar, e
     a alternativa à conta local é não vender. Ela é feita em centavos inteiros, com o mesmo
     arredondamento do `Decimal` do servidor — ponto flutuante aqui apareceria como um
     centavo que não fecha no fim do dia, longe de onde nasceu.
   - **A rede que cai no meio do atendimento não cria uma segunda venda.** A venda aberta no
     servidor é um rascunho: não tem número nem baixa de estoque, é intenção e não fato. O
     pacote do aparelho chega com o mesmo id e **substitui** o conteúdo do rascunho. Sem
     isso o pacote batia na regra do reenvio, respondia "já existia" e desaparecia — o
     rascunho ficava aberto para sempre e a venda que aconteceu não entrava.
   - **Venda cancelada no servidor é recusada**, e fica na fila com o motivo à mostra.
     Ressuscitá-la calada esconderia que duas pessoas discordaram sobre a mesma venda.
5. **Entrar sem rede.** ✅ feita em 17/11/2026, na forma decidida pelo dono do projeto —
   sessão persistida com validade de 30 dias, e não PIN com hash no disco. Era o que
   faltava para o offline-first servir para algo: recarregar a página na lavoura batia na
   tela "Sem conexão", e a fila de sincronização existia sem ter como ser alcançada.

Cada fatia é uma alteração própria, com teste e checagem por mutação.

**O que continua faltando para a operação inteira:** a tela de **pulverização** sem rede. A
resposta 5 põe três telas no escopo, e duas estão de pé — ponto de venda e clientes. Lançar
planejamento e campo sem sinal é a próxima, e é a que o piloto usa de verdade na lavoura.
