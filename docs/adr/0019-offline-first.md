# ADR 0019 — Offline-first: a escrita acontece no aparelho, o servidor continua sendo o dono

> **Renomeada em 04/11/2026, de "local-first" para "offline-first".** O nome anterior fez o
> dono do projeto entender que o dado passaria a morar na máquina do cliente, e ele recusou
> por um motivo certo: *"quero manter o controle, não posso deixar na máquina do cliente"*.
> A decisão nunca foi essa — a decisão 5 sempre disse que o servidor é a verdade e que a
> hospedagem não muda. Era o termo que estava errado: "local-first", no uso corrente,
> sugere dado morando no cliente e sincronizando entre máquinas. O aparelho aqui só
> **adianta** a escrita; ele não vira dono de nada.

- **Data:** 2026-11-03
- **Status:** aceito como direção; **bloqueado para implementação** pelas questões da última
  seção
- **Depende de:** ADR 0001 (monólito modular), ADR 0008 (ponto de venda)
- **Atravessa:** ADR 0004 (ativação por empresa), ADR 0015 (modo de implantação, fora do
  tronco), ADR 0018 (modelo fiscal na transição)

## Contexto

A ADR 0018 levantou uma tensão e não a resolveu: a contingência da norma fiscal é contra a
**SEFAZ**, com o caixa na rede, mas um PDV que é tela conversando com API remota perde o
sistema inteiro quando a internet do cliente cai — antes de chegar perto da SEFAZ.

O dono do projeto corrigiu o escopo, e a correção é maior que o PDV:

> *"O conceito de Offline-First (Local-First) NÃO é restrito ao PDV. Ele é o padrão global
> de todo o Decko. Quer esteja um produtor rural registrando dados do módulo Agro no meio do
> campo sem sinal, um vendedor cadastrando cliente no galpão, ou o caixa vendendo no PDV."*

Isso tem apoio no que o produto já é. O módulo agro nasceu de um formulário preenchido **no
campo**, e o discovery do agro descreve exatamente a situação de quem anota em papel porque
não há sinal. O alvo declarado no `CLAUDE.md` inclui celular fraco. A ausência de rede não é
exceção nesse público: é segunda-feira.

### O que o sistema faz hoje, conferido no código

| | Hoje |
|---|---|
| Quem gera o `id` | O **servidor**: `default=uuid.uuid4` nos modelos |
| Número da venda | Contador no banco, travado por `ON CONFLICT DO UPDATE`, para dois caixas simultâneos não repetirem |
| Idempotência | **Não existe** em nenhuma rota |
| Baixa de estoque | Mesma transação da venda, via `comercial.registrar_movimento` |
| Isolamento entre empresas | Row Level Security, **no PostgreSQL** |
| Trilha de auditoria | Escrita no servidor, na transação da ação |

Nenhuma dessas é um detalhe que se ajusta: cada uma é uma premissa de "o servidor é o lugar
onde as coisas acontecem".

## Decisão

**1. Escrita nasce no aparelho.** Criar cliente, registrar venda, lançar nota, atualizar lote do
agro — tudo é gravado primeiro no aparelho, com identidade gerada ali, e a interface
responde na hora. Nenhuma tela espera resposta de rede para confirmar o que a pessoa fez.

**2. A identidade vem da origem.** O `id` passa a ser um UUID gerado no cliente, e não no
servidor. É o que torna a sincronização idempotente sem inventar um segundo campo de
correlação: reenviar o mesmo registro é reenviar a mesma chave primária.

**3. Fila de pendentes, sincronizada sozinha.** As escritas vão para uma fila local
(*outbox*). Quando a rede volta, a fila esvazia em segundo plano, sem a pessoa pedir e sem
tela de "sincronizando".

**4. A API aceita o mesmo pacote duas vezes sem duplicar.** Reenvio por oscilação de sinal é
o caso normal, não o excepcional. Rota de escrita responde igual na segunda vez.

**5. O servidor continua sendo a verdade depois da sincronização.** Isto não é
peer-to-peer nem banco distribuído. O aparelho adianta a escrita; o servidor consolida,
valida e é de onde sai relatório, fechamento e documento fiscal. A hospedagem gerenciada da
ADR 0015 não muda.

**6. Isto resolve a tensão da ADR 0018.** A contingência contra a rede passa a ter resposta:
há onde enfileirar. A contingência contra a SEFAZ continua sendo o que a ADR 0018 descreve.

## O que isto quebra, e que não dá para fingir que não

Esta seção existe porque a decisão é cara, e o preço precisa estar escrito antes de alguém
começar.

**Número de venda não pode ser atribuído offline.** O contador é uma linha travada no banco,
e dois caixas sem rede não têm como combinar. Ou o número só existe depois da sincronização
— e o cupom impresso na hora não o mostra — ou ele deixa de ser sequencial. **Número fiscal
é pior ainda**: série e número de NFC-e têm exigência legal de sequência, e é precisamente
para isso que existe o regime de contingência da ADR 0018. Operacional e fiscal se separam
aqui, e a ADR 0018 já os separou.

**Estoque pode ser vendido duas vezes — com dois aparelhos, não com um.** A baixa é na mesma
transação da venda. Um caixa sozinho offline não inventa estoque: ele saiu com o saldo
sincronizado e vai subtraindo. O furo aparece quando **há mais de uma origem** — dois caixas,
ou um caixa e uma entrada de nota, ou um ajuste feito no escritório — e cada uma enxerga uma
fotografia diferente do mesmo saldo. O que o sistema faz quando as
duas chegam — aceitar e deixar negativo, recusar a segunda, avisar alguém — é **regra de
negócio**, e o `CLAUDE.md` proíbe supor.

**Dado pessoal sai do banco protegido.** O isolamento entre empresas é feito pelo
PostgreSQL. Um armazenamento local não tem Row Level Security: passa a existir CPF e dado de
cliente no disco de um PC de balcão e no celular de um vendedor. Isso tem consequência de
LGPD direta — criptografia em repouso, apagamento ao sair, e o que acontece quando o aparelho
é perdido.

**Conflito deixa de ser hipótese.** Duas edições do mesmo cliente, as duas offline. "Quem
chegou por último ganha" perde dado em silêncio, que é o pior resultado possível num cadastro
fiscal.

**A trilha de auditoria ganha dois tempos.** Uma ação feita às 14h02 no campo e sincronizada
às 17h30 tem duas horas verdadeiras. A trilha precisa guardar as duas, e saber qual delas
responde a pergunta "quando isso foi feito" é o tipo de coisa que só se descobre errada numa
fiscalização.

**O pacote engorda.** Acabamos de cortar a abertura de 379 kB para 258 kB. Camada local,
fila e *service worker* reconstroem parte disso. Pela regra 5 do `CLAUDE.md`, peso é
requisito — então o ganho de resiliência tem de ser medido contra o que custa carregar.

## Questões em aberto — bloqueiam a implementação

1. **Qual conflito resolver como.** Por entidade: venda não conflita (é append), cadastro
   conflita. Sem regra escrita, não se implementa sincronização.
2. ~~**Estoque negativo é aceito?**~~ **Respondida em 04/11/2026 pelo dono do projeto.**
   A venda registra o que aconteceu de verdade: o cliente levou a mercadoria, então o
   sistema subtrai. Recusar a venda por divergência criaria exatamente o que o controle de
   estoque existe para impedir — mercadoria saindo sem registro, "caixa 2", recebimento que
   ninguém lançou.

   Nas palavras dele: *"se não bater a conta é aí que tá o pulo do gato que o dono quer,
   manter o controle do estoque. (...) Se houver, ele já sabe que teve algum problema no
   dia."* **A divergência é o produto, não o defeito.** Saldo negativo é um aviso com
   endereço — diz quanto faltou e em qual venda —, e escondê-lo trocaria um número
   desconfortável por um furo invisível.

   O que fica para a implementação: a divergência precisa **aparecer** na sincronização,
   não só existir no banco.
3. **Até quando um aparelho pode ficar offline** antes de a sincronização ser recusada? Um
   dia é operação; três meses é outro problema.
4. **O que fica disponível offline.** Vender offline exige o catálogo no aparelho. O
   catálogo inteiro de uma distribuidora cabe num celular fraco?
5. **Permissão revogada enquanto o aparelho está fora.** A pessoa foi desligada às 9h e o
   aparelho sincroniza às 18h o que ela fez às 11h. Aceita ou recusa?
6. **Quanto disto vale para quais telas.** Escrita no aparelho em consolidação mensal e em
   trilha de auditoria provavelmente não paga o custo. "Global" é a direção; a lista por tela não foi
   feita.

## Alternativas consideradas

**Só o PDV offline.** É o que a ADR 0018 supunha. Descartado pelo dono do projeto, com
razão: o agro nasceu de uma prancheta no meio da lavoura, e é lá que a falta de sinal é
regra.

**Cache de leitura, escrita sempre online.** Mais barato e metade da solução: a tela abre sem
rede e não deixa fazer nada. Para quem está no campo ou no balcão, não deixar registrar é o
mesmo que estar fora do ar.

**Banco distribuído com resolução automática de conflito.** Resolve o conflito no papel e
troca o problema por outro: sem a regra de negócio escrita, a resolução automática decide por
conta própria qual versão do cadastro fiscal sobrevive.
