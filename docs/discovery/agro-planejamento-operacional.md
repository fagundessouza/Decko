# Discovery — Planejamento Operacional (módulo Agro)

**Fonte:** formulário real em uso pela AgroDrone (talão de 4 vias), fornecido por Nathan Henrique
Fagundes Gomes (CEO, AgroDrone — Jataí/GO) em 19/10/2026.
**Status:** requisito validado em campo. Não é suposição.

> Este documento é a fonte da verdade do módulo Agro. Qualquer campo do modelo de dados que não
> estiver rastreado até uma linha deste formulário precisa de justificativa explícita.

---

## 1. O processo hoje (fluxo manual)

1. O piloto executa a aplicação (pulverização por drone).
2. Durante/após o voo, anota os dados no talão de papel — incluindo **12 leituras meteorológicas**
   (3 datas × matutino/vespertino × início/final × 3 grandezas).
3. Em escritório, transcreve tudo para planilha Excel.
4. Consolida no fim do mês e faz upload manual no sistema do MAPA.

O talão tem 4 vias: Branca (empresa), Rosa (cliente), Azul (piloto), Amarela (fixa).

## 2. Onde está a dor (ordenado por tempo desperdiçado)

| # | Dor | Automação proposta |
|---|---|---|
| 1 | 12 leituras meteorológicas preenchidas à mão, muitas vezes **de memória ou retroativamente** | GPS + timestamp → API meteorológica → preenchimento automático, com payload bruto guardado como prova |
| 2 | Coordenadas da área digitadas em grau/minuto/segundo | GPS do celular → conversão decimal→DMS automática |
| 3 | Tabela de produtos copiada do receituário agronômico | Foto do receituário → OCR + LLM → linhas pré-preenchidas |
| 4 | Croqui da área desenhado/anexado manualmente | Importar log de voo do drone → gerar croqui com linhas de aplicação e seta do vento |
| 5 | Horímetro inicial recopiado do voo anterior | Puxar automaticamente do último planejamento da mesma aeronave |
| 6 | Retranscrição para Excel no fim do mês | Consolidação mensal nativa + exportador |

## 3. Risco jurídico — o que torna este produto crítico

O formulário registra **Temperatura Máxima**, **Umidade Relativa Mínima** e **Velocidade do Vento**
como *parâmetros de planejamento* — ou seja, limites que a aplicação não deveria ultrapassar.

Aplicar defensivo com vento fora da janela causa **deriva** (o produto atinge a lavoura vizinha),
o que gera processo judicial e autuação. Hoje o registro do clima é feito depois, de memória —
então a empresa não tem prova defensável do que estava acontecendo no momento da aplicação.

**Consequência de produto (dois recursos, não um):**

- **Preventivo:** se o clima lido pela API violar os parâmetros do planejamento, o app alerta
  **antes/durante** a aplicação. Isso evita o processo, não só documenta.
- **Probatório:** cada leitura guarda `source`, `provider`, `payload_bruto`, `lat/lon` e
  `captured_at` imutáveis. Isso é a prova pericial.

Essa dupla função é o que diferencia o Decko de "um formulário digital".

## 4. Mapa de campos → modelo de dados

### 4.1 Cabeçalho — dados fixos da empresa aplicadora (`tenant`)

| Campo no formulário | Entidade | Observação |
|---|---|---|
| Nº Registro MAPA | `tenant.registro_mapa` | |
| CREA / CDA | `tenant.crea`, `tenant.cda` | |
| CNPJ / Insc. Estadual / Insc. Municipal | `tenant.cnpj`, `.inscricao_estadual`, `.inscricao_municipal` | CNPJ conferido na entrada — ver "Formato do CPF/CNPJ" |
| Rodapé (endereço/telefone/email) | `tenant.rodape` | linha única, como sai no papel |
| Logo | — | ver questão aberta Q2: define se o branding é por empresa ou por modelo de documento |
| PLANEJAMENTO OPERACIONAL Nº | `operational_plan.numero` | sequencial **por tenant** |

### 4.2 Contratante e área

| Campo | Entidade |
|---|---|
| Contratante | `client.nome` |
| CNPJ/CPF | `client.cpf_cnpj` — ver "Formato do CPF/CNPJ" abaixo |
| Propriedade | `property.nome` |
| Município / UF | `property.municipio`, `.uf` |
| Coordenadas da Área (º S / º W) | `property.lat`, `.lon` (decimal) — renderizado em DMS no PDF |

#### Formato do CPF/CNPJ

Guardado sem máscara e conferido pelo dígito verificador antes de entrar. O mesmo documento
digitado com e sem pontuação é o mesmo contratante, o que faz a unicidade por documento valer.
Na emissão, a máscara volta: o papel é conferido a olho contra o documento do contratante.

- **CPF:** 11 dígitos, módulo 11.
- **CNPJ:** 14 posições. Desde julho de 2026 as doze primeiras aceitam letras maiúsculas além
  de números; os dois dígitos verificadores continuam numéricos. O módulo 11 permanece, com
  cada caractere convertido pelo valor ASCII menos 48 — os algarismos mantêm o próprio valor
  e `A` vale 17.
- **Fonte:** ["CNPJ alfanumérico — Perguntas e Respostas", Receita Federal][rfb-cnpj],
  pergunta 14. O exemplo trabalhado de lá (`12.ABC.345/01DE-35`) está fixado em
  `apps/api/tests/test_documents.py`, com as somas intermediárias conferidas uma a uma.
- **O que a fonte oficial não diz:** o caso em que o resto é 0 ou 1. O dígito é 0, porque 11 e
  10 não cabem em uma posição — mesmo tratamento do CNPJ numérico, em uso há décadas.
- O formato numérico continua válido: nenhuma empresa precisou trocar de número.

[rfb-cnpj]: https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/cnpj/cnpj-alfanumerico.pdf

### 4.3 Guia de Aplicação

| Campo | Entidade | Tipo |
|---|---|---|
| Cotação | `operational_plan.cotacao` | |
| Cultura | `operational_plan.cultura` | enum: pastagens, cana_de_acucar, cafe, milho, citrus, eucalipto, soja, outras + `cultura_outras_texto` |
| Tipo de aplicação | `operational_plan.tipos_aplicacao` | enum múltiplo: maturador, herbicida, fungicida, inseticida, adubacao, outros + `tipo_outros_texto` |
| Tamanho da Área (ha) | `operational_plan.area_ha` | decimal |

### 4.4 Tabela de produtos (N linhas) → `plan_product_item`

`produto` (FK `product`), `formulacao`, `classe_toxicologica`, `dosagem_ha`, `volume_ha`,
`total_produto`, `adjuvante`.

`formulacao` e `classe_toxicologica` pertencem ao cadastro do produto (`product`), não à linha —
são copiados para a linha no momento da emissão para preservar o histórico caso o cadastro mude.

### 4.5 Receituário Agronômico → `agronomic_prescription`

`numero`, `emitido_em`, arquivo digitalizado (MinIO) + resultado do OCR.
O formulário remete as precauções de uso ao receituário, então o vínculo é obrigatório.

### 4.6 Equipamento e parâmetros → `operational_plan`

| Campo | Entidade |
|---|---|
| Barras/Bicos · Eletrostático · Sólidos · Atomizadores · Outros | `equipamento_tipo` (enum) |
| Modelo / Tipo / Ângulo | `equipamento_modelo`, `_tipo_bico`, `_angulo` |
| Temperatura Máxima | `param_temperatura_maxima_c` |
| Umidade Relativa Mínima | `param_umidade_relativa_min_pct` |
| Largura da Faixa | `param_largura_faixa_m` |
| Altura do Voo | `param_altura_voo_m` |
| Velocidade do Vento | `param_velocidade_vento_max_kmh` |
| Nome/CREA/Assinatura/Data | responsável técnico → `signature` (papel `eng_agronomo`) |
| Croqui anexado | `operational_plan.croqui_file_id` — **anexo obrigatório** |

### 4.7 Aeronave → `aircraft` + `maintenance_log`

`prefixo`, e o bloco **Controle de Manutenção (Horas x Voo)**:
linhas `inicial` / `final` × colunas `voo`, `translado_ida`, `operacao`, `translado_volta`, `total`.

Também: `tempo_servico`, `ha_aplicado`, `emitiu_relatorio_dgps` (bool),
`termo_higrometro_utilizado` (texto).

### 4.8 Condições Meteorológicas → `weather_reading` ⭐

Estrutura do formulário: 3 blocos de data × período (matutino/vespertino) × momento (início/final),
cada um com Hora, Temperatura (°C), Umidade Relativa (%), Velocidade do Vento (km/h).

O modelo **não** deve fixar 3 datas — guarda N leituras e o PDF renderiza em blocos de 3.

```
weather_reading
  plan_id
  data, periodo (matutino|vespertino), momento (inicio|final)
  hora, temperatura_c, umidade_relativa_pct, velocidade_vento_kmh
  source (api|manual|sensor)          -- auditoria
  provider, payload_bruto (jsonb)     -- prova pericial, imutável
  lat, lon, captured_at
  violou_parametro (bool, derivado)   -- alerta de deriva
```

### 4.9 Assinaturas → `signature`

Quatro papéis, cada um com registro profissional próprio:

| Papel | Registro |
|---|---|
| `eng_agronomo` | CREA |
| `piloto_agricola` | CANAC |
| `tec_agricola_executor` | CREA |
| `proprietario_preposto` | CPF / nome completo |

MVP: PDF idêntico ao talão para impressão e assinatura física.
Fase 2: assinatura digital (avaliar ICP-Brasil — ver Q5).

## 5. Escopo do MVP

Dentro:

- Cadastros: tenant, cliente, propriedade, aeronave, produto.
- Criação do Planejamento Operacional via wizard mobile.
- Captura de GPS + clima automático com registro probatório.
- Alerta de violação de parâmetro (vento/temperatura/umidade).
- Geração do PDF fiel ao talão atual.
- Listagem e consolidação mensal.

Fora (fases seguintes):

- OCR do receituário, croqui a partir do log de voo, entrada por voz/LLM,
  busca semântica, integração automatizada com o portal do MAPA, assinatura digital.

**Critério de aceite do MVP:** Nathan consegue emitir um Planejamento Operacional completo em
campo, pelo celular, sem papel, e o PDF resultante é aceito no lugar do talão atual.

### 4.8 Consolidação mensal

Fecha a dor nº 6: hoje o mês inteiro é retranscrito do talão para uma planilha. O fechamento
é montado a partir do que já está registrado — uma linha por planejamento, como uma via do
talão — e sai em CSV com ponto e vírgula, vírgula decimal e BOM, que é o que o Excel em
português abre sem corromper acentos nem transformar o CNPJ em notação científica.

O resumo traz quantidade, área total, totais por produto e **quantos planejamentos tiveram
leitura fora dos limites planejados** — o número que a empresa precisa ver antes de enviar o
mês, não depois de ser autuada.

Nada é descartado em silêncio: planejamento sem data de aplicação não pertence a mês nenhum
e é contado à parte, e rascunho aparece na lista com o status à mostra.

**Isto não é o envio ao MAPA.** Qual sistema recebe e em que formato é a questão Q1, ainda
sem resposta; deduzir um layout "do MAPA" seria inventar regra em domínio regulado. A tela
diz isso ao operador, para ninguém supor que baixar a planilha cumpriu a obrigação.

## 6. Respostas do Nathan — 27/10/2026

Nathan respondeu por mensagem, numerando as respostas por conta própria. **A numeração dele
não é a desta lista** — a resposta 8, por exemplo, é sobre o talão ser de terceiro, que aqui
é a Q2. Por isso as respostas vêm abaixo pelo assunto, com o texto dele entre aspas, e não
encaixadas à força num número que pode não ser o certo.

Roteiro usado na conversa: `perguntas-para-o-nathan.md`. O roteiro é descartável; esta lista
não. Não há Q10: ela tratava do formato do CPF/CNPJ e foi respondida pela Receita Federal —
ver "Formato do CPF/CNPJ" na seção 4.2.

### 6.1 Respondido

**Quem assina (Q5, Q13).**
> *"eu sou o agrônomo da empresa e piloto. Faço o relatório e pego assinatura do produtor
> (muitas vezes esse cara é o responsável pela sua lavoura, quando tem Agronomo, pego dele)"*
>
> *"o certo seriam várias vias, mas se der pra encaminhar via PDF, cliente assina com gov, ou
> uma caneta no celular ou tablet."*

Duas coisas caem daqui. A primeira: **a mesma pessoa é o agrônomo e o piloto** — os quatro
papéis de assinatura do formulário não são quatro pessoas. A segunda: **assinatura digital
serve**, tanto gov.br quanto desenho na tela. A Q5 estava travando uma etapa do roadmap e
deixou de travar — ver `docs/discovery/assinaturas-dois-modulos.md`.

**Numeração (Q12).**
> *"pode ser número corrido."*

O sistema já numera por empresa a partir de 1, sequencial. Nada a mudar.

**O talão e o arquivo (Q2, Q7).**
> *"esse foi um amigo que fez e mandou, usamos ele em campo, depois que passamos pra planilha
> do Excel eu arquivo ele por 2 anos, o físico."*
>
> *"nunca me pediram, eu não sei o tempo ao certo, eu guardo uns 2 anos. Se tiver digital fica
> melhor, da pra ficar lá resto da vida."*

O talão é modelo de conhecido, não produto de terceiro com identidade própria: o cabeçalho é
da empresa dele, e a premissa da seção 4.1 se confirma. Retenção: dois anos é o costume, não
uma exigência que alguém tenha cobrado. Guardar indefinidamente no digital resolve.

**Clima (parte da Q8).**
> *"temperatura você confronta informação pela data, hora e algum aplicativo, por ex: 'fonte:
> UAV Forecast' (esse o app que eu uso) então o ideal é teu aplicativo fique conectado com
> algum programa de monitoramento do clima, que já vai dar em tempo real essa informação, sem
> precisar informar manualmente."*
>
> *"vento informo o do app que uso do clima."*

É exatamente o que a captura automática já faz, com uma diferença que vale corrigir: **ele
cita a fonte no documento** ("fonte: UAV Forecast"). O PDF precisa imprimir de onde veio a
leitura, e o dado já está guardado — ver seção 4.8.

**Produto e área (Q9).**
> *"você informa a dose x área, nesse caso você faz o mapa da área. Essa informação pode ser
> preenchida após a aplicação. Que facilita caso o cliente peça pra fazer um 'bico a mais
> ali'."*

O total é dose × área, e **a área é a aplicada, não a planejada** — por isso pode ser
preenchida depois. O campo digitado continua certo; o que muda é que o sistema pode sugerir a
conta quando a área aplicada estiver preenchida.

**Volume (Q3).**
> *"o certo é emitir de toda operação, hoje eu faço a metade ou menos pela trabalheira kk"*

Não é um número, mas diz o essencial: **ele emite menos documento do que deveria, e o motivo é
o trabalho**. O ganho do produto não é só tempo, é conformidade.

**Drone (Q4, parte da Q6).**
> *"uso Dji. Tem um app que mostra os hectares, relatório de voos, mostra vazão, altura, tempo
> de voo, coordenadas, tem tudo lá."*

DJI, com aplicativo que já tem hectares, vazão, altura, tempo de voo e coordenadas. O croqui
automático e o preenchimento a partir do voo ficam viáveis — **falta saber o que o aplicativo
exporta como arquivo**, que é o que a pergunta original pedia e continua sem resposta.

**Horímetro (Q14).**
> *"zera não. Essa informação eu nem coloco. Mas se quiser por, o drone mostra quantas horas
> ele tem de voo, teria que informar antes da aplicação, mas é um trabalho a mais. Vou ver se
> posso deixar sem (pq copiaram do avião)"*

Não zera, e **ele não preenche**. O bloco de manutenção já é todo opcional no modelo, então
não há o que mudar — e a dor nº 5 (puxar o horímetro do voo anterior) perde prioridade: não
adianta automatizar um campo que ninguém usa. Ele vai confirmar se pode sair do formulário.

### 6.2 Requisito novo

**Cadastro de pilotos.**
> *"Ideal era pensa tbm, uma forma da empresa cadastrar os pilotos, cada um fazia seu
> relatório. Isso ajuda hein."*

A empresa cadastra seus pilotos e o planejamento aponta para quem voou. Hoje o nome do piloto
só existe como texto dentro da assinatura, redigitado a cada documento.

### 6.3 Respondido pela norma, não pelo Nathan

Em 27/10/2026 metade do que estava "esperando o Nathan" foi achado no texto das normas —
ver `agro-normas-mapa.md`, com as fontes. Resumo do que saiu de pergunta:

- **Q1 e Q11.** O relatório mensal vai para o **SIPEAGRO**, por sistema eletrônico, até o
  dia 15 do mês seguinte, com cinco informações agregadas por município/UF: aeronave, área
  total e horas de execução, tipo de atividade, e marca comercial com volume e dosagem.
  A planilha do Nathan é transcrição intermediária dele, não o formato de destino.
- **Q2.** O talão **é** o anexo da IN 2/2008. O conhecido dele imprimiu o modelo da norma.
- **Q7.** Dois anos é o mínimo legal, nas duas normas. O costume dele é a lei.
- **Q8.** Nenhuma norma fixa número: os limites são declarados no planejamento pelo
  responsável técnico, e a bula do produto é a origem recomendada. **Confirma o modelo
  atual** e tira o risco de retrabalho que esta pergunta carregava.
- **Q4 (resto).** A DJI não publica API; o caminho é exportar **KML** pelo Agras Management
  Platform. O arquivo de exemplo continua útil, agora só para conferir o conteúdo.

E apareceu uma exigência que ninguém tinha visto: a norma de drone pede **direção do
vento**, que o sistema ainda não guarda.

### 6.4 Ainda em aberto

- **Registro no SIPEAGRO.** Ele está registrado como operador de ARP? A norma exige, e sem
  isso o relatório mensal não tem para onde ir.
- **Volume por mês.** Dimensiona o ganho, e nenhuma norma responde.
- **CAAR e aplicador aeroagrícola remoto.** A Portaria 298 cria essas figuras; saber se
  existem na operação dele diz se entram no cadastro.
- **Pilotos e login.** "Cada um fazia seu relatório": cada piloto terá usuário próprio no
  sistema, e deve ver só os planejamentos dele? Ou o cadastro serve só para não redigitar o
  nome? Enquanto não houver resposta, o cadastro é só cadastro.
