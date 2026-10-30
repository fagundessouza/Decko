# O que a norma do MAPA já responde — pesquisa em fonte primária

**Levantado em:** 27/10/2026
**Método:** leitura do texto integral das normas, baixadas do `gov.br`, não de resumo de
terceiro. Os trechos citados foram extraídos dos PDFs oficiais.

> **Por que este documento existe.** Metade das questões abertas do agro estava esperando
> o Nathan responder coisa que a norma já define. Ele é operador: sabe o que faz na
> prática, e o que ele faz pode até divergir do que a norma exige. Para requisito
> regulado, a fonte é a norma; para preferência de operação, é ele. A regra 6 do
> `CLAUDE.md` pede requisito documentado — e documentação oficial é documentação.

---

## 1. Qual norma rege a operação do Nathan

Ele voa drone. Drone de pulverização é **ARP — aeronave remotamente pilotada**, e quem
rege é a **Portaria MAPA nº 298, de 22/09/2021**, não a IN 2/2008, que trata de aviação
agrícola tripulada.

As duas convivem: segundo levantamento secundário, o art. 25 da Portaria 298 mantém a
IN 2/2008 e a IN 1/2012 aplicáveis às operações com ARP no que couber. **Na dúvida entre
as duas, a específica de ARP manda.**

**Vigência:** não encontrei revogação da Portaria 298/2021. Há consulta pública propondo
consolidá-la com a IN 2/2008, e notícia do MAPA de 2025 anunciando decreto e portaria
novos, sem confirmação de publicação. **Conferir antes de qualquer entrega que dependa
disso** — é o tipo de coisa que muda e ninguém avisa.

## 2. O registro de cada aplicação (Portaria 298/2021, art. 10)

Os dados que a operação precisa registrar:

| Exigido pela norma | No Decko |
|---|---|
| Cultura tratada | `cultura` ✅ |
| Área tratada em hectares | `area_ha` / `ha_aplicado` ✅ |
| Tipo de atividade | `tipos_aplicacao` ✅ |
| Marca comercial, **volume e dosagem aplicada** | `plan_product` ✅ |
| Altura do voo | `param_altura_voo_m` ✅ |
| **Dados meteorológicos: temperatura, umidade relativa, direção e velocidade do vento** | `weather_reading` — ⚠️ **falta a direção do vento** |
| Aeronave (identificação da ARP conforme ANAC) | `aircraft.prefixo` ✅ |
| Tipo/modelo de ponta de pulverização | `equipamento_bico_tipo` / `equipamento_bico_angulo` ✅ |

**Duas diferenças que importam:**

1. **Direção do vento é exigida e não é guardada.** O formulário da IN 2/2008 pede só a
   velocidade; a norma de ARP pede direção *e* velocidade. O provedor de clima já devolve
   a direção — é campo a acrescentar, não integração nova.
2. **"Durante a aplicação"**, e não "no início e ao final". A IN 2/2008 pede as duas
   pontas; a de ARP pede o acompanhamento. O modelo atual, de leituras com carimbo de
   tempo, atende as duas — é mais do que qualquer uma pede, e está certo assim.

## 3. O relatório mensal — a resposta da Q1 e da Q11

**Portaria 298/2021, art. 11 e art. 19, I.** É aqui que a maior incógnita do projeto se
resolve:

> *"As informações relativas às atividades realizadas durante o mês deverão ser
> consolidadas no relatório mensal, **via sistema eletrônico**, com os seguintes dados:
> I - município/UF do local de aplicação; II - aeronave utilizada (identificação da ARP);
> III - total da área aplicada (ha) **e horas de execução (h)**; IV - tipo de atividade
> (aplicação de agrotóxico, de fertilizante, de inoculante, de corretivo, semeadura e
> outros); e V - marca comercial, volume e dosagem aplicada."*
>
> *"O relatório mensal deverá ser disponibilizado ao MAPA até o **décimo quinto dia do mês
> subsequente**."*
>
> *"Os operadores de ARP registrados no MAPA deverão: I - apresentar relatórios mensais de
> atividades no **SIPEAGRO**."*

**O que isso significa para o código.** A consolidação de hoje exporta uma linha por
planejamento, com colunas aproximadas a partir do formulário: número, status, contratante,
documento, propriedade, leituras, violações. Nenhuma delas é pedida.

O que a norma pede é **agregado por município/UF e aeronave**, com cinco informações. São
listas diferentes, não a mesma lista com nomes trocados:

| Norma pede | Decko tem |
|---|---|
| Município/UF | ✅ |
| Aeronave (ARP) | ✅ |
| Total de área aplicada (ha) | ✅ |
| **Horas de execução** | `tempo_servico` — existe, não entra no CSV |
| Tipo de atividade | ✅ |
| Marca comercial, volume e dosagem | ✅ nos itens do plano |

**A planilha do Nathan deixa de ser bloqueio.** Ela é a transcrição intermediária dele, não
o formato de destino — o destino é o SIPEAGRO. Continua sendo útil ver a dele, para
conferir contra o que o sistema produz, mas não para descobrir as colunas.

## 4. Retenção — a resposta da Q7

**Portaria 298/2021, art. 19, III:** registros das aplicações, mapas de aplicação e
receituários arquivados pelo prazo **mínimo de dois anos**, em meio físico ou digital.

A IN 2/2008, art. 9º §9º, diz o mesmo para a aviação tripulada: *"Os relatórios
operacionais deverão ser arquivados pelas empresas pelo prazo mínimo de dois anos."*

Os dois anos do Nathan são exatamente o mínimo legal. **Guardar indefinidamente no digital
atende com folga**, e nada na norma impede.

## 5. Limites de vento e temperatura — a resposta da Q8

**Nenhuma das duas normas fixa número.** O que elas exigem é registrar e interromper:

- IN 2/2008, art. 9º §7º: a aplicação é acompanhada por técnico *"interrompendo-se quando
  os parâmetros básicos atingirem os limites máximos de segurança"*.
- IN 2/2008, art. 9º, X: os "parâmetros básicos de aplicação" — **limites** de temperatura,
  velocidade do vento e umidade relativa — são parte do **planejamento**, declarados pelo
  responsável técnico com nome, assinatura e CREA.
- A bula de cada agrotóxico traz as condições climáticas recomendadas para aquele produto.

**Isso confirma o modelo atual e tira um risco de retrabalho.** Os limites ficam no
planejamento, declarados pelo agrônomo, e não numa tabela fixa — que era a dúvida. O que a
pesquisa acrescenta é que a **bula do produto** é a origem recomendada desse número: cabe
guardar o limite sugerido no cadastro do produto e propô-lo ao montar o planejamento,
mantendo a palavra final com o agrônomo. Isso é melhoria, não correção.

## 6. O talão não é de terceiro — a resposta da Q2

O anexo da IN 2/2008 **é** o formulário que o Nathan usa. O PDF oficial traz, literalmente,
os mesmos blocos: *"Parâmetros Básicos de Aplicação — Temperatura Máx., Umidade Relativa
Mín., Velocidade do Vento Máx."*, *"Croqui da área com indicador da direção dos tiros e
sentido do vento"*, *"Condições Meteorológicas na Aplicação"* com matutino/vespertino e
inicial/final, e as quatro assinaturas.

O *"amigo que fez e mandou"* imprimiu o modelo da norma em talão. O cabeçalho é da empresa
dele, e a premissa da seção 4.1 do discovery se confirma: identificação por empresa, não
por modelo de documento.

**E há um prazo que ninguém tinha mencionado:** IN 2/2008, art. 9º §5º — o relatório
operacional é assinado pelo engenheiro agrônomo responsável *"após as aplicações
aeroagrícolas, no prazo máximo de **dez dias**"*.

## 7. DJI — o que dá para importar

Não existe API pública documentada do SmartFarm nem do Agras Management Platform. O que
existe, e é suficiente:

- **Exportação de rota em KML** pelo DJI Agras Management Platform: seleciona-se os
  registros de voo, abre-se "View Flight Route" e exporta. Também pela aba de gestão de
  equipe.
- O KML do SmartFarm é **mais pobre em telemetria** que o log de voo de outras aeronaves
  DJI — serve para o traçado, não para vazão e altura instantâneas.
- Ferramentas de terceiro (Flight Reader, AirData) leem logs `.txt` do Agras e devolvem
  CSV, e sincronizam voos do SmartFarm. São intermediários pagos, não a fonte.

**Consequência:** o croqui a partir do voo é viável por **importação de KML**, operação
manual do piloto, sem integração. Pedir um arquivo de exemplo ao Nathan continua valendo,
mas agora é para conferir o que o KML dele traz — não para descobrir o formato.

## 8. O que continua sendo pergunta para o Nathan

Depois desta pesquisa, sobra pouco, e o que sobra é mesmo dele:

1. **Ele está registrado no SIPEAGRO como operador de ARP?** A norma exige; se ele não
   estiver, o relatório mensal não tem para onde ir, e isso muda a prioridade do que
   construímos.
2. **Quantos planejamentos por mês?** Dimensiona o ganho, e nenhuma norma responde.
3. **Ele usa o CAAR / tem aplicador aeroagrícola remoto?** A Portaria 298 cria essas
   figuras; saber se existem na operação dele diz se entram no cadastro.
4. **A planilha dele**, agora só para conferência — não mais para descobrir colunas.

## Fontes

- [Portaria MAPA nº 298, de 22/09/2021 — operação de ARP para aplicação de agrotóxicos](https://www.gov.br/agricultura/pt-br/assuntos/insumos-agropecuarios/aviacao-agricola/legislacao/portaria-mapa-298-de-22-09-2021.pdf) — texto integral, lido
- [Instrução Normativa MAPA nº 2, de 03/01/2008 — aviação agrícola](https://www.gov.br/agricultura/pt-br/assuntos/insumos-agropecuarios/insumos-agricolas/agrotoxicos/arquivos/in2.pdf) — texto integral, lido
- [Registro no MAPA para pulverizar com drone: SIPEAGRO e o relatório do dia 15 (2026)](https://irlenmenezes.com.br/registro-drone-mapa-sipeagro-pulverizacao-2026/) — secundária, usada só para vigência
- [Cartilha "Drones na lavoura", Sistema FAEP (2025)](https://www.sistemafaep.org.br/wp-content/uploads/2025/08/Cartilha-Drones-na-lavoura.pdf) — secundária
- [Nota Técnica 01/2025 sobre pulverização com drones — Ibram Brasil](https://ibrambrasil.org.br/pulverizacao-agrotoxicos-drones-nota-tecnica-01-2025/) — secundária, menciona a consulta pública de consolidação
- [DJI Agras: exportação de KML pelo Agras Management Platform](https://help.acreconnect.io/en/articles/10186084-downloading-dji-kml-flight-logs) — secundária
- [AirData — DJI AGRAS / SmartFarm](https://app.airdata.com/wiki/Help/DJI+AGRAS) — secundária, sobre o conteúdo do KML
