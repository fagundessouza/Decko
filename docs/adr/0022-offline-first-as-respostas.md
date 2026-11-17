# ADR 0022 — Offline-first: as respostas que faltavam

**Data:** 17/11/2026
**Estado:** **proposta** — aguarda confirmação do dono do projeto
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

**Proposta:** o aparelho guarda os operadores que **já entraram nele**, cada um com o hash
Argon2id do **PIN** — nunca da senha, e nunca em texto. Sem rede, o PIN abre uma sessão
local, com as permissões da última sincronização.

Com três limites, e eles são o preço:

1. **Só PIN, nunca senha.** O PIN já existe para o balcão e já tem bloqueio por tentativa
   (ADR 0020). A senha é a credencial de verdade e não se espalha por aparelho.
2. **Validade de 7 dias sem sincronizar.** Depois disso o aparelho para de abrir sessão
   local e exige rede. É o que limita o estrago de um aparelho perdido ou de alguém
   desligado, e casa com a janela da resposta 2.
3. **Só em aparelho confiado.** O dono marca a estação como confiável; o celular de
   qualquer um não vira chaveiro por ter entrado uma vez.

**O que isso custa, dito claramente:** passa a existir CPF, cadastro de cliente e hash de
PIN no disco de um PC de balcão e no celular de um piloto, fora do PostgreSQL e portanto
fora do Row Level Security. Isso tem consequência de LGPD — o armazenamento local precisa
ser apagado ao sair, e aparelho perdido é incidente a tratar, não contratempo.

## O que isto não resolve

- **Número de venda e número fiscal** continuam como a ADR 0019 e a 0018 descrevem: o
  `numero` já é nulo até finalizar, e a numeração fiscal segue o regime de contingência.
- **Dois caixas offline podem vender o mesmo último item.** Decidido em 04/11: o saldo
  fica negativo e isso aparece. Esta ADR só acrescenta que a divergência precisa ter
  endereço — qual venda, qual aparelho, quanto faltou.

## Por onde começar, se as respostas forem aceitas

Em fatias que valem sozinhas, na ordem:

1. **Identidade na origem e rotas idempotentes.** O `id` passa a vir do aparelho e reenviar
   o mesmo pacote deixa de duplicar. Não muda nada visível e é a base de todo o resto.
2. **Fila local e cadastro de cliente offline.** A fila mais simples, na tela mais simples.
3. **Leitura guardada para o PDV e o agro**, pelo recorte da resposta 3.
4. **Venda offline**, com a divergência de estoque aparecendo na sincronização.
5. **Entrada sem rede pelo PIN**, com os três limites da resposta 6.

Cada fatia é uma alteração própria, com teste e checagem por mutação. Nenhuma delas é
pequena, e a 4 e a 5 são as caras.
