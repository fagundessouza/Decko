# Discovery — identificação fiscal do produto (módulo Comercial)

**Fonte:** Lucas Fagundes Souza, de quando era vendedor na Fujioka Distribuidor, em
24/10/2026.
**Status:** requisito vindo de operação real, não de suposição. As perguntas da seção 4
continuam em aberto e **não** foram implementadas.

---

## 1. A situação relatada

Parte da carteira de clientes do distribuidor trabalha com **licitação**. Na hora de montar
a proposta, esse comprador não pergunta o preço primeiro: pergunta **qual é o NCM do
produto**, porque o edital exige a classificação fiscal do item ofertado. Sem o NCM na
mão, o vendedor tinha de ligar para a empresa, procurar na nota de entrada ou no site do
fabricante — com o cliente esperando.

O mesmo cliente pede o **código do produto** para organizar o estoque dele e para conferir
o que chegou contra o que foi pedido.

## 2. O que isso exige do cadastro

| O que o comprador pergunta | Onde fica no Decko |
|---|---|
| NCM do produto | `comercial_produto.ncm` — 8 dígitos |
| CEST, quando o produto é de substituição tributária | `comercial_produto.cest` — 7 dígitos |
| Código do produto para o estoque dele (SKU) | `comercial_produto.codigo`, que já existia |
| Código de barras | `comercial_produto.gtin`, que já existia |

**O SKU não virou campo novo.** O produto já tinha `codigo`, único por empresa, que é
exatamente isso: o código com que a loja chama o produto. Criar um `sku` ao lado deixaria
duas verdades para a mesma coisa, e em seis meses metade do cadastro estaria preenchida só
em um dos dois. O que mudou foi a tela, que agora diz "Código (SKU)" — o problema era de
nome, não de modelo.

## 3. O que foi implementado

- **NCM** — Nomenclatura Comum do Mercosul, 8 dígitos. Aceita digitado com ou sem máscara
  (`2106.90.90` ou `21069090`) e é guardado só com os dígitos. A máscara volta na leitura.
- **CEST** — Código Especificador da Substituição Tributária, 7 dígitos, mesmo tratamento.
  Entrou junto porque só existe acompanhando o NCM: quem precisa de um precisa do outro, e
  deixá-lo para depois custaria uma segunda migração na mesma tabela.
- **Busca por NCM** na listagem de produtos, porque a pergunta do comprador às vezes vem ao
  contrário: *"o que vocês têm no NCM 8544.42.00?"*

**A conferência é de formato, não de existência.** O Decko verifica que são 8 dígitos; não
verifica se aquele NCM existe na tabela da Receita, porque o projeto não tem a tabela. Um
NCM errado mas bem formado passa. Isso está dito aqui para não ser descoberto como defeito
mais tarde — carregar a tabela oficial é item da seção 4.

## 4. Perguntas em aberto — não implementar sem resposta

Tudo abaixo apareceu ao modelar e **não** foi suposto. O domínio é fiscal e regulado.

1. **Origem da mercadoria** (0 a 8, Convênio ICMS): nacional, importada direta, adquirida
   no mercado interno. É obrigatória na NF-e. Vale guardar agora ou entra com o módulo
   fiscal?
2. **CATMAT / CATSER**: o catálogo de materiais do governo federal, usado no Comprasnet. O
   comprador de licitação pedia esse código também, ou só o NCM?
3. **Marca e modelo**: o edital costuma exigir "marca e modelo ofertados". O produto do
   Decko não tem fabricante nem marca. Era pergunta frequente?
4. **Unidade tributável**: a NF-e separa unidade comercial de unidade tributável (vende-se
   em caixa, tributa-se em quilo). A base comercial tem árvore de unidades, mas não marca
   qual é a tributável.
5. **Tabela oficial de NCM**: carregar e validar contra ela exige atualização periódica —
   a tabela muda. Vale a manutenção, ou conferir o formato basta?
6. **CST / CSOSN e CFOP**: dependem do regime da empresa e da operação, não só do produto.
   Ficam fora do cadastro — confirmar.

A regra 6 do `CLAUDE.md` vale aqui inteira: enquanto não houver resposta, o campo não
existe. Melhor um cadastro que não responde tudo do que um que responde errado numa
proposta de licitação.
