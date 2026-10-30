# Discovery — emissão fiscal no comércio

**Fonte:** Lucas Fagundes Souza, em 29/10/2026, de memória, com a observação de que vai
acrescentando conforme lembrar.
**Status:** requisito colhido. **Nada aqui virou código**, e a regra 6 do `CLAUDE.md` vale
inteira: o domínio é regulado, e o que não estiver respondido não é suposto.

Este documento acumula. Cada rodada de lembrança entra aqui, não no código.

---

## 1. O que foi pedido

> *"Emissão fiscal tu pode colocar 2 situações: 1, o cliente emite aquele recibo que sai em
> impressora térmica, porém não é emissão fiscal; e 2, a emissão fiscal. (…) uma das dores
> do comerciante é questão de notas fiscais, o medo de ficar pagando multa ou sonegar
> imposto, ter que declarar o imposto certinho. (…) tem que ser simples e prático, não pode
> ser muito complexo fazer essa emissão, tem que estar de acordo com as portarias, leis,
> tudo direitinho."*

Mais duas lembranças, que a seção 3 confere:

- Um sistema do **SEBRAE** com que "o pessoal conseguia fazer emissão de notas fiscais".
- A **Avalara / AvaTax**, com a vontade de "fazer já no meu sistema uma maneira igual,
  porque aí não precisa ficar contratando serviços".

---

## 2. As duas situações, separadas

### 2.1 Recibo não fiscal em impressora térmica

Documento de cortesia e de controle interno: o que o cliente leva para conferir o que
comprou. **Todo PDV tem**, e o Decko não tem nenhum — hoje o módulo não imprime nada, e
"cupom" só aparece em comentário.

É a parte barata e sem dependência externa: layout, largura de 58 ou 80 mm, e o caminho até
a impressora.

> **O que precisa estar claro no produto, e não só aqui.** O recibo não fiscal **não
> substitui** o documento fiscal onde ele é exigido. Vender emitindo só o recibo é sonegação,
> e um sistema que se apresente como atalho para isso expõe quem o vende — o que vai na
> direção oposta do "tudo direitinho" que foi pedido. A funcionalidade é legítima; o que não
> pode é a posição de alternativa.

### 2.2 Emissão fiscal de verdade

Documento com valor jurídico, autorizado pelo fisco antes de a venda se concluir. No balcão,
é a **NFC-e (modelo 65)** ou, em São Paulo e Ceará, o **SAT-CF-e**. Para venda que não é ao
consumidor final, é a **NF-e (modelo 55)**. Serviço é **NFS-e**, e não entra aqui.

---

## 3. O que foi lembrado, conferido

### 3.1 "API para a Receita" — não é a Receita

A NFC-e e a NF-e são autorizadas pela **SEFAZ do estado**, não pela Receita Federal. O
layout é nacional, definido pelo ENCAT e pelas Notas Técnicas do Portal da NF-e, mas o
**endpoint, o ambiente de homologação e parte das regras são estaduais**.

A consequência prática é a que mais pesa no custo: não é "uma API". É um layout nacional
contra 27 implementações, e o trabalho de suportar o segundo estado não é o mesmo de
suportar o primeiro.

Falta responder: **quais estados**, e em que ordem. Começar por um só é viável; prometer
Brasil inteiro não é.

### 3.2 O emissor do SEBRAE — existe, e não é o que resolve

Confere. A SEFAZ-SP descontinuou o emissor gratuito próprio, e pelo **Convênio 10/17** o
**Sebrae-SP** passou a distribuir e atualizar o emissor gratuito de NF-e (modelo 55) a
partir de julho de 2017.

Dois detalhes que mudam a conclusão:

- É um **aplicativo de mesa** que a pessoa instala e opera, não um serviço com API. Não é
  coisa que o Decko integre; é concorrente do que o Decko faria.
- É **NF-e modelo 55**, não NFC-e de balcão.

O estado atual dele não ficou claro na pesquisa — os registros encontrados param entre 2019
e 2022. **Antes de citar o SEBRAE como referência, confirmar se ainda está de pé.**

### 3.3 Avalara / AvaTax — é cálculo, não emissão

Esta é a correção que mais muda o escopo.

| Produto | O que faz |
|---|---|
| **AvaTax Brasil** | **Motor de cálculo.** Determina qual tributo incide e quanto, a partir de NCM, CEST, origem e destino, regime da empresa e natureza da operação |
| **Mensageria** (veio da compra da Oobj) | **Emissão.** Gera o XML, assina, transmite à SEFAZ e à prefeitura, trata retorno |

São dois produtos porque são dois problemas. "Fazer igual à Avalara" é construir o
**primeiro** — e é ele que responde à dor descrita, não o segundo.

### 3.4 A dor descrita não é emissão

O que foi dito foi *"medo de pagar multa ou sonegar, ter que declarar o imposto certinho"*.

Transmitir o XML não resolve isso. Quem erra o CST, o CFOP ou a alíquota transmite com
sucesso **e erra do mesmo jeito** — e a autorização da SEFAZ não é conferência de que o
imposto está certo. O que resolve é determinação correta: a tabela de regras, mantida.

Ou seja: a dor real do comerciante está no produto **mais caro de manter**, não no mais
difícil de escrever.

---

## 4. O risco de calendário — o achado mais importante

**A reforma tributária está no meio da transição, e o documento fiscal está mudando agora.**

- A **NT 2025.002** altera os leiautes da NF-e (55) e da NFC-e (65) e cria o grupo de IBS,
  CBS e Imposto Seletivo, com `CST-IBS/CBS` e `cClassTrib` por item.
- **2026 é ano de teste**, com alíquotas simbólicas para quem está no regime normal; MEI e
  Simples não destacam IBS/CBS em 2026.
- Há **NT 2026.007**, de agosto de 2026, com campos e validações para contribuinte exclusivo
  de IBS/CBS.
- As datas de obrigatoriedade **divergem entre as fontes** consultadas, que são em maioria
  blogs de software fiscal. **Precisam ser confirmadas no Portal Nacional da NF-e e nas
  notas técnicas oficiais** antes de qualquer decisão.

O que isso significa para o Decko, e vale dizer com todas as letras: **um motor de
determinação tributária escrito hoje contra as regras de hoje nasce com validade conhecida.**
ICMS, PIS, COFINS e ISS estão sendo substituídos por IBS e CBS, e a tabela de regras que é o
coração de um "AvaTax próprio" é exatamente a parte que será reescrita.

Isso não diz "não faça". Diz que a **ordem** importa: emissão (layout, que já tem o grupo
novo definido) envelhece menos que determinação (regras, que estão sendo trocadas).

---

## 5. O que o Decko tem e o que falta

| Peça | Estado |
|---|---|
| NCM e CEST no produto | **Existe** — `apps/api/src/decko/fiscal.py`, conferência de formato |
| Identificação da empresa (CNPJ, IE) | **Existe** — cadastro da empresa |
| Venda com itens, preço e cliente | **Existe** — PDV, com venda identificada |
| Impressão de qualquer coisa | **Não existe** |
| Certificado digital | **Não existe** — nem armazenamento, nem assinatura |
| Geração e transmissão de XML | **Não existe** |
| Determinação tributária | **Não existe** |
| CST, CFOP, CSOSN, origem da mercadoria | **Não existe** — listados como pergunta aberta em `comercial-produto-fiscal.md` |

As perguntas fiscais daquele outro discovery **continuam sem resposta**, e várias delas são
pré-requisito deste: origem da mercadoria, unidade tributável, CST/CSOSN e CFOP.

---

## 6. Perguntas em aberto — não implementar sem resposta

**Escopo e sequência**

1. Qual documento primeiro: **NFC-e** (balcão) ou **NF-e** (venda para empresa)? São
   modelos, regras e públicos diferentes.
2. **Quais estados**, e em que ordem? Um estado é projeto; 27 é produto.
3. São Paulo e Ceará usam **SAT-CF-e**, que é equipamento, não webservice. Entram?
4. Emissão **própria** (Decko fala direto com a SEFAZ) ou **intermediada** (Decko usa uma
   mensageria de terceiro)? Muda o custo, a responsabilidade e o prazo. O pedido foi "não
   contratar serviço", mas a decisão precisa ser tomada sabendo o preço das duas.

**Determinação tributária**

5. Vale construir o motor de cálculo **agora**, no meio da reforma, ou atender primeiro
   quem está no **Simples Nacional**, onde a regra é bem mais simples e que é o regime do
   público-alvo?
6. Quem mantém a tabela de regras quando ela mudar? É trabalho contínuo, não entrega única.

**Operação e responsabilidade**

7. Onde fica o **certificado digital A1** do cliente? Guardar certificado de terceiro é
   responsabilidade séria, e muda os requisitos de segurança da hospedagem.
8. O que acontece quando a SEFAZ cai? **Contingência** é parte da norma, não extra.
9. Quem responde se uma nota sair errada — o lojista, o contador dele, ou quem fez o
   sistema? Precisa estar no contrato antes da primeira nota.
10. O contador do cliente entra no fluxo? Hoje ele é quem fecha o imposto, e o sistema que
    o ignora cria trabalho em vez de tirar.

---

## 7. Fontes consultadas

Pesquisa de 29/10/2026. A maioria dos resultados sobre a reforma são blogs de software
fiscal, **não fontes oficiais** — estão aqui como indício, e as datas precisam de
confirmação oficial.

- [Nota Técnica 2025.002 — IBS/CBS/IS na NF-e e NFC-e](https://blog.tecnospeed.com.br/nota-tecnica-reforma-tributaria-nfe-nfce/)
- [Portal Nacional da NF-e — Reforma Tributária do Consumo](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=YmYqYBW8gGQ%3D)
- [Novo layout fiscal da NF-e em 2026](https://notafiscal.cnt.br/novo-layout-fiscal/)
- [Emissor 4.0 — Sebrae-SP](https://sebrae.com.br/Sebrae/Portal%20Sebrae/UFs/SP/nfe/EMISSOR_4.0-SebraeSP.PDF)
- [Fim do emissor gratuito da SEFAZ e o Convênio 10/17](https://www.coad.com.br/home/noticias-detalhe/76812/emissor-gratuito-de-nf-e-continua-disponivel-em-sao-paulo)
- [AvaTax Brasil — determinação e cálculo de tributos](https://www.avalara.com/br/pt/solucoes/solucao-de-determinacao-e-calculo-de-tributos.html)
- [Mensageria — emissão de documentos fiscais](https://www.avalara.com/br/pt/solucoes/emissao-de-documentos-fiscais.html)
