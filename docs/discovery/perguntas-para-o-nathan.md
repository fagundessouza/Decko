# Roteiro de conversa com o Nathan — questões abertas do módulo Agro

**Para:** Nathan Henrique Fagundes Gomes (CEO, AgroDrone — Jataí/GO)
**Origem:** questões abertas de `agro-planejamento-operacional.md`, seção 6
**Preparado em:** 21/10/2026

**Cópia para levar à reunião:** <https://claude.ai/artifact/7FG54iCvVnB4cMUsjqVZtL> — mesmo
conteúdo, agrupado por risco em vez de listado, e com campo para digitar a resposta na hora.
Este arquivo é a versão versionada junto do projeto; aquele é o que se usa na conversa.

As perguntas numeradas são as mesmas do discovery (Q1–Q9 e Q11–Q14); aqui elas vêm reescritas na
língua de quem opera, ordenadas por quanto destravam, e com espaço para a resposta. As
respostas voltam para a seção 6 do discovery — este roteiro é descartável, o discovery não.

> **O número 10 não existe de propósito.** A Q10 tratava do formato do CPF/CNPJ e foi
> respondida pela própria Receita Federal, não pelo cliente. O número fica vago porque está
> citado em comentários de código e em mensagens de commit; renumerar quebraria as referências.
> O que ficou decidido está no fim deste documento.

---

## Antes de perguntar: peça para ver

Resposta falada sobre formato de arquivo é a menos confiável que existe. Vale mais sair da
conversa com **material** do que com descrição. Em ordem de valor:

1. **A tela do sistema do MAPA**, no momento do envio mensal — de preferência compartilhando a
   tela, ou com fotos. Resolve a Q1 inteira, que é a maior incógnita do projeto.
2. **A planilha de consolidação** que ele preenche hoje, mesmo bagunçada, mesmo de um mês só
   (Q11).
3. **Um talão preenchido de verdade**, não em branco — mostra o que ele escreve de fato em cada
   campo, que costuma ser diferente do que o campo pede.
4. **Um arquivo exportado pelo aplicativo de voo**, de qualquer voo (Q4).

Se a conversa for curta, peça o material e deixe as perguntas para depois. O material responde
várias delas sozinho.

## Se só der tempo de três

| | Por quê |
|---|---|
| **Q5** — assinatura física ou digital | É a única coisa que trava uma etapa já planejada. Sem resposta, não dá para fechar o ciclo do documento. |
| **Q12** — número inicial do planejamento | Se ele está no talão nº 847 e o sistema começar do 1, o registro fica errado já na primeira emissão. É pequeno de arrumar e caro de descobrir tarde. |
| **Q1** — o que sobe para o MAPA | Define se o PDF realmente substitui o talão, que é o critério de aceite do MVP inteiro. |

---

## As perguntas

### Q5. As assinaturas precisam ser de próprio punho?

**Perguntar assim:** "O formulário tem quatro assinaturas — agrônomo, piloto, técnico e o
proprietário. Elas precisam ser à caneta? Se você entregar um PDF, como isso funciona hoje: o
cliente imprime e assina, assina na tela do celular, ou vocês já usam assinatura digital em
alguma coisa?"

**Por que importa:** é a única questão que trava uma etapa já prevista no roadmap. Se for física,
o PDF só precisa imprimir as linhas de assinatura — que é exatamente o que ele já faz, e a etapa
fecha sem código novo. Se aceitar digital, entra um fluxo de assinatura, e aí vale perguntar se
alguém já exigiu certificado ICP-Brasil.

**Resposta:**


---

### Q12. De que número o sistema deve começar a contar?

**Perguntar assim:** "O talão já vem com o número impresso. Em que número você está hoje? Quando
o sistema passar a emitir, ele deve continuar dessa numeração ou pode começar do 1? E se o
talão de papel continuar sendo usado em paralelo por um tempo, como evitar dois documentos com
o mesmo número?"

**Por que importa:** o sistema numera por empresa começando em 1. Se ele está no 847, o primeiro
documento emitido sai com número que já existe no arquivo dele — num registro com efeito legal.
É barato ajustar agora e constrangedor descobrir depois da primeira fiscalização.

**Resposta:**


---

### Q1. Este formulário é o que sobe para o MAPA?

**Perguntar assim:** "Esse formulário do talão é o que vai para o MAPA, ou é um documento seu e
do cliente? No fim do mês você entra em qual sistema para mandar? Dá para me mostrar a tela? Ele
aceita subir um arquivo, ou é digitar campo por campo?"

**Por que importa:** é a maior incógnita do projeto. Decide (a) se o PDF que geramos realmente
substitui o talão — o critério de aceite do MVP —, e (b) se o exportador mensal deve produzir um
layout específico. Hoje a exportação sai em planilha para conferência, e a tela diz explicitamente
que o envio continua sendo feito pelo portal, justamente porque isto está em aberto.

**Resposta:**


---

### Q11. Como é a planilha que você preenche no fim do mês?

**Perguntar assim:** "Me manda a planilha que você preenche no fechamento? Pode ser de um mês só,
do jeito que estiver."

**Por que importa:** com o arquivo em mãos, o CSV sai nas colunas dele, na ordem dele. Hoje as
colunas foram aproximadas a partir dos campos do formulário, o que é um palpite educado.
Se a resposta da Q1 for "upload de arquivo", é o layout do MAPA que manda, e esta pergunta muda
de dono.

**Resposta:**


---

### Q8. O limite de vento e temperatura vem do produto ou do agrônomo?

**Perguntar assim:** "Quando você preenche temperatura máxima, umidade mínima e vento máximo no
planejamento, de onde vem esse número? Está no rótulo do produto, vem no receituário, ou é o
agrônomo que define em cada aplicação?"

**Por que importa:** hoje o alerta de deriva compara a leitura com os limites de **cada
planejamento**, que é como o formulário trata. Se o limite for propriedade do produto, ele deveria
estar no cadastro de produto e ser sugerido automaticamente — menos digitação e menos chance de
alguém preencher um limite frouxo sem perceber. É a pergunta com maior risco de retrabalho.

**Resposta:**


---

### Q13. Com o PDF, quem fica com qual via?

**Perguntar assim:** "O talão tem quatro vias: branca da empresa, rosa do cliente, azul do piloto
e a amarela que fica presa. Com o documento em PDF, quem precisa receber o quê? O cliente ainda
quer papel na mão na hora, ou aceita receber depois por mensagem?"

**Por que importa:** o critério de aceite diz que o PDF substitui o talão, mas o talão não é um
documento — são quatro destinos diferentes. Se o cliente precisa de papel assinado na hora, o
fluxo em campo muda (imprimir? assinar na tela?).

**Resposta:**


---

### Q9. "Total do produto" é copiado ou calculado?

**Perguntar assim:** "Nessa coluna de total do produto, você copia o número do receituário ou faz
a conta na hora? Se faz a conta, multiplica pela área que estava planejada ou pela que você
realmente aplicou?"

**Por que importa:** hoje o campo é digitado, porque calcular com a área errada produziria um
número errado num documento com efeito legal. Se ele confirmar a conta e qual área usar, dá para
calcular e poupar digitação.

**Resposta:**


---

### Q2. O talão é de terceiro?

**Perguntar assim:** "A logo do talão é AgroDrone, mas o rodapé diz DroneTech Brasil, de
Dobrada/SP. Esse talão é comprado pronto de alguém? O cabeçalho é da sua empresa ou é o modelo de
quem imprime?"

**Por que importa:** o sistema já guarda o cabeçalho por empresa — registro no MAPA, CREA, CDA,
inscrições e rodapé —, partindo da premissa de que a identificação é de quem aplica. Se o talão
for modelo de terceiro, parte desse cabeçalho pertence ao modelo do documento, não à empresa, e a
modelagem muda.

**Resposta:**


---

### Q3. Quantos planejamentos por mês?

**Perguntar assim:** "Quantos planejamentos você emite por mês, mais ou menos? Tem época do ano
que concentra?"

**Por que importa:** dimensiona o ganho real de tempo — é o número que diz se o projeto vale o que
está custando. Também decide se o cache de consultas meteorológicas precisa existir (o ADR 0003
diz que só se justifica com volume).

**Resposta:**


---

### Q4. Qual drone, e o que o aplicativo de voo exporta?

**Perguntar assim:** "Qual drone vocês usam? Depois do voo, o aplicativo gera algum arquivo ou
relatório — mapa da área, arquivo para baixar, histórico do voo? Consegue me mandar um exemplo?"

**Por que importa:** define se o croqui pode ser gerado a partir do log de voo em vez de desenhado
à mão. É a dor nº 4 da lista, e está em fase posterior — mas a resposta decide se é viável.

**Resposta:**


---

### Q6. Como o croqui é feito hoje?

**Perguntar assim:** "E o croqui da área, com a direção dos tiros e a seta do vento — como você
faz? Desenha à mão no talão, ou tira de algum aplicativo?"

**Por que importa:** anda junto com a Q4. Se hoje já sai de um aplicativo, talvez baste anexar o
que ele já produz, em vez de gerar um novo.

**Resposta:**


---

### Q7. Por quanto tempo as vias precisam ser guardadas?

**Perguntar assim:** "Por quanto tempo você precisa guardar as vias do talão? Alguém já te pediu
documento de aplicação antiga? Quanto tempo depois?"

**Por que importa:** define política de retenção e de backup. Também diz se documento antigo pode
continuar sendo editado ou se, passado certo ponto, ele precisa ficar imutável.

**Resposta:**


---

### Q14. O horímetro é contínuo por aeronave?

**Perguntar assim:** "O horímetro que você anota no início e no fim: ele é um contador que só
sobe, por aeronave? Zera em manutenção? Quem lê esse número — você no painel, ou sai do
aplicativo?"

**Por que importa:** a dor nº 5 propõe puxar o horímetro inicial do voo anterior da mesma
aeronave. Para isso o número precisa ser contínuo e previsível. Se ele zera em manutenção, a
automação precisa saber disso ou vai sugerir número errado.

**Resposta:**


---

## O que já está decidido — não precisa perguntar

Registrado para a conversa não reabrir o que já tem resposta:

- **Formato do CPF/CNPJ (ex-Q10).** Respondido pela Receita Federal, não pelo cliente. CPF tem 11
  dígitos; o CNPJ tem 14 posições e, desde julho de 2026, as doze primeiras aceitam letras, com os
  dois dígitos verificadores numéricos. Já está conferido na entrada, com o exemplo oficial fixado
  em teste. Detalhes em `agro-planejamento-operacional.md`, seção 4.2.
- **O que já funciona:** emissão do PDF no formato do talão, captura de clima por coordenada e
  horário com registro probatório, alerta de violação de parâmetro, cadastros pela tela e
  fechamento mensal com exportação para planilha.

## O que fazer com as respostas

Cada resposta vai para a seção 6 de `agro-planejamento-operacional.md`, substituindo a questão
correspondente por uma linha de requisito. Pergunta respondida deixa de ser pergunta: se virar
requisito, vira linha do modelo ou do roadmap na mesma alteração.
