# ADR 0009 — Identidade de produto e entrada pela nota do fornecedor

- **Data:** 2026-10-24
- **Status:** aceito
- **Requisito:** `docs/discovery/comercial-entrada-por-nota.md`

## Contexto

O mesmo refrigerante chega escrito `COCA COLA 2L RET` numa nota e
`Refrigerante Coca-Cola 2 Litros Retornável` na outra. Se cada nota criar um produto, o
estoque fica com dois cadastros e meio saldo em cada — e o dono, que conta a gôndola,
deixa de confiar no sistema.

Então entrada de nota e identidade de produto são o mesmo problema. Ler o XML é a parte
fácil; decidir **qual produto é aquele item** é o que faz a funcionalidade valer.

## Decisões

### 1. GTIN identifica; NCM só filtra

O pedido sugeria casar por NCM. O NCM classifica a **categoria**: `2202.10.00` cobre
Coca-Cola, Pepsi e Guaraná, de todos os tamanhos. Casar por ele juntaria o produto do
concorrente no mesmo cadastro.

Quem identifica item, marca, modelo e tamanho é o **GTIN** — é a finalidade dele. O NCM
entra como filtro negativo: NCM diferente é indício forte de que não é o mesmo produto, e
serve para não sugerir absurdo.

### 2. Três chaves, em ordem de confiança, e só duas automáticas

| Chave | Automática? |
|---|---|
| GTIN igual | **Sim.** É identidade global |
| Mesmo `cProd` do mesmo CNPJ emitente | **Sim**, depois de confirmada uma vez |
| Nome parecido | **Nunca.** Sugere; quem decide é o lojista |

Semelhança de nome é palpite. Palpite automático que acerta 95% das vezes erra o estoque
em 5% das entradas, e ninguém descobre qual — então ele nunca liga sozinho. Aparece
ordenado, com a razão à vista, e espera o clique.

### 3. A confirmação vira regra: o sistema aprende

Quando o lojista confirma que `COCA COLA 2L RET` do CNPJ `00.000.000/0001-00` é o produto
X, grava-se uma linha de equivalência. A nota seguinte daquele fornecedor entra sozinha.

É o que faz a ferramenta melhorar com o uso, em vez de perguntar a mesma coisa todo mês.
A tabela é `comercial_produto_fornecedor`, e fica no `comercial` porque é identidade de
produto — o PDV também vai querer achar produto por GTIN.

### 4. Nada entra no estoque antes de a nota ser conferida

A nota importada fica num estado próprio (`rascunho`), com os itens casados, sugeridos ou
em branco. Nenhum produto é criado e nenhum movimento é lançado enquanto o lojista não
confirmar a nota inteira.

O contrário — importar e lançar direto — transformaria um XML errado em correção manual
de estoque, que é o trabalho que esta funcionalidade existe para eliminar.

### 5. Importar é compra, e compra é módulo próprio

O ADR 0006 já havia decidido: *"Compra, venda e PDV são módulos sobre esta base, não parte
dela"*. Então a importação mora em `compras`, que declara
`depends = ["core", "comercial"]` — ver ADR 0007.

O que fica no `comercial` é a **identidade**: a tabela de equivalência e o serviço que
responde "este item é qual produto meu?". Identidade de produto é do catálogo, não da
compra; a venda vai precisar do mesmo.

### 6. XML primeiro, e só ele

O pedido falava em QR code, XML, PDF e JSON. Só o XML entra agora, e os outros não são
"depois" por preguiça:

- **QR code da NFC-e não contém os itens.** Ele leva ao portal da SEFAZ com a chave de
  acesso; obter o XML a partir da chave exige certificado digital A1/A3 e manifestação do
  destinatário.
- **PDF do DANFE** depende de OCR, que é a Fase 6. E o DANFE é desenho de impressão: ler
  dele é menos confiável que ler o XML, que é o documento.
- **JSON de nota fiscal não é um padrão.** Sem saber de qual ERP, não há o que
  implementar.

O XML é o documento oficial, é exato, já chega ao lojista por e-mail e não depende de
certificado nem de OCR.

## Consequências

- Aparece um aplicativo novo na vitrine: **Compras**. Instalá-lo traz a base comercial.
- O produto criado a partir da nota nasce com GTIN, NCM, CEST e descrição do fornecedor,
  que é mais do que o cadastro manual costuma receber.
- A conversão de unidade continua dependendo de a embalagem estar cadastrada. A nota diz
  `CX`, não diz quantas unidades tem a caixa — está na seção 6 do discovery.
- **Risco:** equivalência confirmada errado gruda o item errado para sempre naquele
  fornecedor. Mitigação: a tela mostra o que será ligado antes de ligar, e a equivalência
  pode ser desfeita.
