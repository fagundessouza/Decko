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
| CNPJ / Insc. Estadual / Insc. Municipal | `tenant.cnpj`, `.inscricao_estadual`, `.inscricao_municipal` | |
| Logo + rodapé (endereço/telefone/email) | `tenant.branding` | ver questão aberta Q2 |
| PLANEJAMENTO OPERACIONAL Nº | `operational_plan.numero` | sequencial **por tenant** |

### 4.2 Contratante e área

| Campo | Entidade |
|---|---|
| Contratante | `client.nome` |
| CNPJ/CPF | `client.cpf_cnpj` |
| Propriedade | `property.nome` |
| Município / UF | `property.municipio`, `.uf` |
| Coordenadas da Área (º S / º W) | `property.lat`, `.lon` (decimal) — renderizado em DMS no PDF |

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

## 6. Questões abertas — perguntar ao Nathan

- **Q1.** Este formulário é o que sobe para o MAPA, ou é documento interno/para o cliente? Qual é
  exatamente o sistema do MAPA usado no envio mensal, e qual formato ele aceita?
- **Q2.** A logo é AgroDrone mas o rodapé é "DroneTech Brasil — Dobrada/SP". O talão é de terceiro?
  Isso define se o branding do PDF é por tenant ou por modelo de documento.
- **Q3.** Volume: quantos planejamentos por mês? (dimensiona o ganho real de tempo)
- **Q4.** Qual drone/modelo, e o que o software de voo exporta (CSV, KML, log DGPS)? Define a
  viabilidade do croqui automático.
- **Q5.** A assinatura precisa ser física, ou o cliente/órgão aceita digital?
- **Q6.** Como o croqui é produzido hoje?
- **Q7.** Por quanto tempo as vias físicas precisam ser guardadas? (define retenção e backup)
- **Q8.** Existe limite legal de vento/temperatura por produto, ou o parâmetro é definido caso a
  caso pelo agrônomo? (define se a regra de alerta é por produto ou por planejamento)
- **Q10.** O cadastro aceita CPF (11 posições) e CNPJ (14 posições, as doze primeiras
  alfanuméricas desde julho de 2026, pelos dois dígitos verificadores numéricos — Instrução
  Normativa RFB nº 2.229). Falta conferir o dígito verificador: no CNPJ alfanumérico o cálculo
  usa o valor ASCII do caractere menos 48, e a fonte oficial precisa ser lida antes de virar
  código que recusa cadastro. Enquanto isso, um documento digitado errado entra no sistema e
  sai impresso no documento legal.
- **Q9.** `total_produto` é digitado a partir do receituário ou calculado? Se calculado, a
  multiplicação usa a área planejada ou a área efetivamente aplicada? Hoje o campo é digitado,
  porque calcular com a área errada produziria um número errado num documento com efeito legal.
