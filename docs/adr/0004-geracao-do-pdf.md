# ADR 0004 — Geração do Planejamento Operacional em PDF

- **Data:** 2026-10-21
- **Status:** aceito para o MVP
- **Revisita:** depois da validação em campo (Fase 3), quando o documento impresso for
  conferido contra o talão real

## Contexto

O módulo agro passou a emitir o Planejamento Operacional como PDF. O documento substitui um
talão de quatro vias preenchido à mão, e quem vai lê-lo — operador, contratante, engenheiro
agrônomo e, em disputa, um perito — já conhece o papel de cor.

Três restrições vêm do uso real:

1. **O leitor não vai ser treinado.** Se a ordem das seções mudar, a conferência deixa de
   ser visual e passa a exigir leitura, o que custa tempo no campo.
2. **O documento tem função probatória.** O mesmo motivo que fez o registro meteorológico
   guardar o payload íntegro (ver `docs/adr/0003-provedor-de-clima.md`) vale aqui: o que
   sai impresso precisa refletir o que está gravado, sem campo editável no caminho.
3. **O aparelho que emite costuma ser um celular em rede ruim.** O PDF não pode depender de
   o cliente ter um navegador capaz de imprimir bem, nem de uma segunda chamada para
   renderizar.

## Decisão

O PDF é montado no backend com **ReportLab** (`modules/agro/src/decko_modules/agro/pdf.py`),
em A4 retrato, e devolvido por `GET /agro/plans/{plan_id}/pdf` como `application/pdf` com
`Content-Disposition: attachment`, sob a permissão `agro.plan.export`.

A estrutura reproduz o talão seção por seção, na mesma ordem: cabeçalho, Guia de Aplicação,
Equipamento/Parâmetros/Aeronave, Condições Meteorológicas e encerramento com observações e
as quatro assinaturas.

**Nenhum campo novo é acrescentado ao formulário.** As violações de parâmetro detectadas na
captura meteorológica entram em "Observações", que já existe no talão.

O renderizador recebe um `PlanDocument` — uma dataclass montada por
`service.build_document()` — e não objetos do ORM. A montagem dos dados e o desenho são
etapas separadas.

Coordenadas saem em grau/minuto/segundo com a letra do hemisfério
(`modules/agro/src/decko_modules/agro/geo.py`), porque é o formato que o formulário pede,
embora o sistema guarde grau decimal.

## Motivo

**ReportLab e não HTML→PDF.** O talão é dirigido por grade: caixas de largura fixa, rótulo
pequeno acima do valor, tudo encaixado em uma folha. Isso é o modelo de layout do ReportLab
(`Table` + `TableStyle`), enquanto em HTML seria lutar contra o fluxo do texto. Além disso,
WeasyPrint ou um navegador headless acrescentam uma dependência nativa pesada a um projeto
que trata leveza como requisito funcional.

**No backend e não no cliente.** O documento precisa sair igual em qualquer aparelho, e o
cliente que o emite é justamente o mais fraco da cadeia. Gerar no servidor também mantém o
documento fora do alcance de qualquer manipulação no navegador antes da impressão.

**Não acrescentar campo.** A tentação era criar uma coluna "violação" ao lado de cada
leitura. O documento legal não prevê essa coluna; um campo a mais transforma um formulário
conhecido em um formulário novo, e tira do operador a conferência visual que o papel já
dava. "Observações" é onde esse tipo de ressalva é escrita hoje.

**Dataclass em vez do ORM.** O desenho não precisa de sessão de banco e não deve decidir o
que carregar. Separar as duas etapas mantém o `pdf.py` sem consulta implícita e deixa a
montagem dos dados — que é onde mora a regra — em um lugar só.

## Consequências

- **A fidelidade ainda não foi provada.** O que existe é a estrutura reproduzida a partir
  do discovery. A conferência contra o talão impresso acontece na Fase 3, com o operador.
  Até lá, "fiel ao talão" é intenção verificada por teste de conteúdo, não por comparação
  com o original.
- O teste (`modules/agro/tests/test_pdf_export.py`) extrai o texto com `pypdf` e verifica
  que os campos obrigatórios saíram — identificação, coordenadas em DMS, produtos,
  parâmetros, leituras e a ressalva de violação. Não compara imagem: quebra de layout que
  não derrube o texto passa despercebida.
- ReportLab entra como dependência do módulo `agro` (`reportlab>=4.4`), não do núcleo. Um
  cliente que não instala o módulo não carrega a biblioteca.
- A logo e o rodapé da empresa aplicadora ainda não entram no documento: dependem da
  questão **Q2** do discovery, que não foi respondida.
- Assinatura continua sendo campo em branco para caneta. Assinatura digital é Fase 2 do
  próprio discovery e depende da questão **Q5**.

## Alternativas consideradas

**WeasyPrint / navegador headless (HTML + CSS).** Reaproveitaria vocabulário do frontend,
mas traz dependência nativa grande, dificulta o controle milimétrico da grade e colocaria
um motor de renderização inteiro no caminho de um documento de uma página.

**Preencher um PDF-formulário do talão original.** Seria a maior fidelidade possível. Foi
descartada porque não existe o arquivo-fonte do talão — ele é um impresso gráfico — e
porque a estrutura ainda vai mudar com o uso real.

**Gerar no cliente (`pdf-lib`, `jsPDF`).** Dispensaria a chamada ao servidor, mas faria o
documento depender do aparelho e colocaria a montagem do conteúdo probatório no lado mais
fácil de adulterar.
