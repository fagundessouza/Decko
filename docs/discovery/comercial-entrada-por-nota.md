# Discovery — entrada de produtos pela nota do fornecedor

**Fonte:** Lucas Fagundes Souza, da experiência como vendedor na Fujioka Distribuidor, em
24/10/2026.
**Status:** requisito vindo de operação real. As perguntas da seção 6 continuam em aberto.

---

## 1. O que foi pedido

Cadastrar produto digitando tudo à mão, item por item, a cada nota que chega. A nota já
traz o nome, a quantidade, o preço, o NCM e o código de barras — e mesmo assim o lojista
redigita.

O pedido tem duas metades:

1. **Ler a nota** — por QR code, XML, PDF, JSON, "entre outros".
2. **Não duplicar o cadastro** — e esta é a parte difícil.

## 2. O problema real: o mesmo item com nomes diferentes

> *"compro em um distribuidor e eles emitem o nome do item abreviado em umas notas e
> outros emitem o mesmo item ou mesmo produto com o nome completo"*

Duas notas, de dois fornecedores, do mesmo produto:

| Fornecedor | `xProd` na nota |
|---|---|
| Distribuidor A | `COCA COLA 2L RET` |
| Distribuidor B | `Refrigerante Coca-Cola 2 Litros Retornável` |

Se cada nota criar um produto, o estoque fica com dois cadastros do mesmo refrigerante,
cada um com meio saldo. O dono conta a gôndola, não bate com nenhum dos dois, e perde a
confiança no sistema inteiro.

**O limite é igualmente firme na outra direção:** Coca-Cola 2L e Coca-Cola 600ml são
produtos diferentes. Coca-Cola e Pepsi, idem. O que se quer agrupar é o **mesmo item** —
mesma marca, mesmo modelo, mesmo tamanho — escrito de formas diferentes.

## 3. NCM não resolve isto

O pedido sugeria o NCM como chave (*"talvez por esses códigos que adotamos de ncm né? nao
sei"*). Ele não serve, e vale registrar por quê, porque a ideia é natural:

**O NCM classifica a categoria, não o item.** `2202.10.00` é "águas, incluindo as águas
minerais, adicionadas de açúcar" — e cobre Coca-Cola, Pepsi, Guaraná, de todos os
tamanhos e de todas as marcas. Casar por NCM juntaria o refrigerante do concorrente no
mesmo cadastro.

O que o NCM faz bem é o contrário: **eliminar candidato absurdo**. Se dois itens têm NCM
diferente, quase certamente não são o mesmo produto. Ele entra como filtro, não como
identidade.

## 4. O que identifica o item de verdade

Em ordem de confiança. A nota fiscal eletrônica traz todos eles.

| # | Chave | Campo na NF-e | Confiança |
|---|---|---|---|
| 1 | **GTIN** (código de barras) | `cEAN` | Identifica item, marca, modelo e tamanho no mundo inteiro. É para isso que ele existe |
| 2 | **Código do produto no fornecedor** | `cProd` + CNPJ do emitente | O mesmo fornecedor usa sempre o mesmo código para o mesmo item. Vale para aquele fornecedor |
| 3 | **Semelhança do nome** | `xProd` | Nunca identifica sozinho. Serve para **sugerir**, e quem decide é o lojista |

A chave 2 é aprendida: quando o lojista confirma que `COCA COLA 2L RET` do fornecedor A é
o produto *Coca-Cola 2L Retornável*, essa ligação fica guardada. Na nota seguinte do mesmo
fornecedor, o item entra sozinho.

É assim que o sistema melhora com o uso em vez de perguntar a mesma coisa todo mês.

## 5. Por onde a nota entra

| Caminho | Situação |
|---|---|
| **XML da NF-e / NFC-e** | **Implementado.** É o arquivo que o fornecedor manda por e-mail e que o contador já recebe. Traz tudo: `cProd`, `cEAN`, `xProd`, NCM, CEST, unidade, quantidade e valor |
| **QR code da NFC-e** | **Não implementado.** O QR não contém os itens: ele leva à consulta no portal da SEFAZ, com a chave de acesso. Baixar o XML a partir da chave exige certificado digital A1/A3 e manifestação do destinatário — é infraestrutura, não tela |
| **PDF do DANFE** | **Não implementado.** Depende de OCR, que é a Fase 6 do roadmap. E DANFE é desenho de impressão: o que se lê dele é menos confiável que o XML, que é o documento |
| **JSON** | **Não implementado.** Não existe um JSON padrão de nota fiscal no Brasil. Se for o formato de algum ERP específico, é preciso saber qual |

O XML foi escolhido primeiro porque é o documento oficial, é exato, é o que já chega ao
lojista hoje, e não depende de certificado nem de OCR.

## 6. Perguntas em aberto — não implementar sem resposta

1. **Certificado digital**: o lojista tem A1/A3? Sem ele não há consulta por chave de
   acesso, e o QR code continua sem caminho.
2. **Conversão de unidade**: a nota vem em `CX` com 12 unidades. O Decko sabe converter
   se a embalagem estiver cadastrada, mas a nota não diz quantas unidades tem a caixa.
   Perguntar ao lojista na conferência, ou guardar por fornecedor?
3. **Preço de custo**: a nota traz `vUnCom`. Atualizar o custo do produto a cada entrada,
   sempre? Só quando subir? Nunca, sem o lojista mandar?
4. **Nota de devolução e de transferência**: entram pelo mesmo caminho? Têm CFOP próprio.
5. **Produto sem GTIN**: muito item tem `cEAN` como `SEM GTIN`. Nesse caso sobra o código
   do fornecedor e a semelhança. Confirmado que é aceitável?
6. **Quem confere**: a conferência da nota é do dono ou de qualquer um com permissão de
   estoque? Hoje exige `compras.nota.conferir`.
