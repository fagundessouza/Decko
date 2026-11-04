# ADR 0018 — O modelo fiscal atravessa a transição sem reescrita

- **Data:** 2026-11-03
- **Status:** aceito
- **Depende de:** ADR 0004 (ativação de módulo por empresa), ADR 0007 (dependência entre
  módulos), ADR 0008 (ponto de venda), ADR 0017 (meios de pagamento)
- **Tensiona:** ADR 0015 (modo de implantação e licença) — ver a seção "A contingência
  tensiona a hospedagem". **Essa ADR ainda não está no tronco**: vive em
  `feature/adr-implantacao`, sem pull request, e é por isso que há um buraco entre 0014 e
  0016 na numeração
- **Leia junto:** `docs/discovery/comercial-emissao-fiscal.md`, seções 4.1 e 6

## Contexto

O Decko não emite documento fiscal: registra a venda, baixa o estoque e imprime um recibo
sem valor fiscal. Antes de escrever a primeira linha de emissão, há uma pergunta de forma a
responder, e ela não é sobre imposto — é sobre o que o banco guarda.

O calendário está confirmado no ADCT, com a redação da EC 132/2023, e a seção 4.1 do
discovery traz artigo por artigo. O que importa aqui é uma consequência que nenhuma das
fontes consultadas destacou:

**De 2026 a 2032 um mesmo cupom carrega os dois regimes.** ICMS em redução por frações e
IBS subindo, lado a lado, no mesmo documento. Não existe um dia de virada em que o modelo
velho possa ser apagado. São sete anos de convivência, e depois disso ainda há documentos
antigos para reimprimir e defender.

E a regra se mexe enquanto se escreve: a LC 227/2026, de janeiro deste ano, alterou cerca de
120 dispositivos da LC 214/2025, e o texto da lei no Planalto já mostra artigos revogados
por ela.

## Decisão

**1. O documento fiscal é uma entidade própria, não colunas na venda.**

Hoje `pdv_venda.status` descreve a venda: aberta, finalizada, cancelada. O documento fiscal
tem vida própria e outro vocabulário — autorizado, pendente, em contingência, rejeitado,
cancelado — e uma venda pode gerar mais de uma tentativa até autorizar. Misturar os dois
estados numa coluna só força a venda a mentir sobre si mesma.

Esta é a decisão mais importante deste ADR, e a única que não depende de nenhuma regra
tributária: vale igual antes e depois da reforma.

**2. Tributo é linha, não coluna.**

Os nomes mudam em data marcada e convivem por sete anos. Colunas chamadas `icms`, `pis`,
`cofins` obrigariam a uma migração a cada fase da transição, e a uma tabela que no fim fica
cheia de colunas mortas que ninguém tem coragem de remover porque documento antigo ainda
aponta para elas.

Então o tributo de cada item é uma linha: qual tributo, base, alíquota, valor, e a
classificação que o leiaute pedir (`CST`, `cClassTrib` e o que vier). Acrescentar IBS, CBS
ou Imposto Seletivo passa a ser inserir linha, não alterar schema.

É o desenho que normalmente se evita, e aqui ele é o certo por um motivo específico: **o
conjunto de tributos é legalmente aberto e muda em calendário conhecido**, e a consulta que
importa é somar por documento, não cruzar tributo com tributo.

**3. O que foi autorizado é guardado como foi, e nunca recalculado.**

O XML autorizado e o protocolo são o artefato legal. Reimprimir em 2031 um cupom de 2028
precisa reproduzir o documento **como ele foi autorizado** — com as alíquotas daquele ano e
os tributos que existiam. Recalcular com as regras do dia da reimpressão produziria um papel
que não corresponde a nada e que não defende ninguém numa fiscalização.

Na prática: o documento guarda o que foi enviado e o que voltou, íntegros, e a reimpressão
lê, não calcula.

**4. Determinação tributária é módulo próprio, atrás de porta.**

Mesmo padrão da ADR 0017 para pagamento, pelo mesmo motivo: a tabela de regras é a parte que
será reescrita, e ela não pode morar no `pdv` nem no núcleo. O PDV pede o cálculo a uma
porta; quem responde é um módulo instalável por empresa.

Isso também deixa a sequência livre: dá para emitir no Simples Nacional, onde a regra é
simples, sem ter um motor completo — e trocar o módulo depois sem tocar no caixa.

**5. Contingência é estado do documento, não caminho de erro.**

A venda se conclui; o documento nasce pendente e vai para uma fila. A autorização é buscada
depois, com retentativa, e a rejeição tem tratamento próprio. Escrever isso como tratamento
de exceção no fim do fluxo é como se constrói um caixa que trava quando a SEFAZ oscila.

**6. Emissão e determinação são módulos distintos.**

Emissão envelhece menos — o leiaute já tem o grupo novo definido. Determinação é o que está
sendo reescrito. Separados, a parte estável não é refém da instável.

## A contingência tensiona a hospedagem

Vale dizer antes que alguém descubra implementando: **"contingência" aqui tem dois sentidos,
e o Decko hoje só pode atender a um.**

A norma pensa em contingência contra a **SEFAZ**: o caixa está na rede, a SEFAZ é que não
responde. Esse caso a decisão 5 resolve.

O outro é contingência contra a **rede**. Pela ADR 0015 — que decidiu hospedagem gerenciada
como padrão, porque não há como visitar 50 ou 100 clientes — o PDV é uma tela que conversa
com uma API remota. Se a internet do cliente cai, o caixa não perde a
SEFAZ: perde o Decko inteiro, antes de chegar perto da SEFAZ. Nenhuma fila de pendentes
resolve isso, porque não há onde enfileirar.

Atender ao segundo caso exige operação local em alguma forma — e isso contraria aquela
decisão, que foi tomada com um argumento forte e ainda válido. **Este ADR não a reabre**;
registra que emissão fiscal em comércio
de balcão a põe em questão, e que a resposta precisa ser dada antes de prometer NFC-e a um
lojista — não depois.

## Consequências

- Nada disto se implementa agora. O ADR existe para que o modelo nasça certo quando houver
  decisão sobre as questões da seção 7 do discovery, que seguem sem resposta.
- Duas mudanças de modelo aparecem antes da emissão e podem ser feitas sem ela: **CPF avulso
  no cupom** — hoje identificar é apontar para um `cliente` cadastrado, e o balcão pede o CPF
  de quem não é cliente — e **terminal de caixa**, que não existe como entidade, de modo que
  duas máquinas do mesmo operador são indistinguíveis.
- Guardar XML autorizado é guardar documento com CPF e valor por anos. Entra no mesmo
  cuidado de LGPD e de backup restaurado que o `NEGOCIO.md` já lista como bloqueio.
- Tributo em linha custa uma junção a mais em toda leitura de documento. É o preço, e é
  menor que uma migração por fase da transição.

## Alternativas consideradas

**Colunas por tributo, migrando a cada fase.** É o que a maioria dos sistemas fiscais fez
antes da reforma, quando o conjunto de tributos era estável por décadas. Deixou de ser.

**Esperar 2033 e implementar só o regime novo.** Ignora que o cliente precisa emitir
**agora**, e que documento emitido hoje tem de ser reimprimível em 2033.

**Um campo JSON com "os impostos".** Resolve a flexibilidade e perde a conferência: sem
tipo, nada impede gravar alíquota como texto, e a soma de um documento vira interpretação.
O que se quer é conjunto aberto **com** estrutura, que é uma tabela filha.
