# ADR 0006 — Base comercial compartilhada

- **Data:** 2026-10-21
- **Status:** aceito

## Contexto

Ferragista, supermercado, lanchonete, restaurante, distribuidora e loja de veículos são
negócios diferentes, mas a auditoria do Odoo 20 mostra que a vertical é **fina**:
`pos_restaurant` declara uma única dependência e é quase só dado-semente. O peso está na
base compartilhada — produto, unidade, estoque, preço.

O Decko não tem essa base. Sem ela, cada vertical teria de inventar a sua, que é como se
chega aos 696 módulos entrelaçados que o próprio Odoo trata como dívida.

Os requisitos abaixo vêm das anotações do dono do projeto, não de suposição:

- *"organização de produtos tanto em unidade, quanto caixas, quanto caixas de atacado"*
- *"controle rigoroso de validades, lotes"*
- *"cadastrar produtos no estoque com as quantidades certinhas"* a partir de nota fiscal

## Decisões

### 1. Unidade de medida é uma árvore, não um par de fatores

Copiado do Odoo 20, que mudou justamente para isto: cada unidade declara **quanto vale em
relação à sua unidade de referência**, e o fator absoluto é o produto recursivo até a raiz.

```
Unidade (raiz, fator 1)
└── Caixa com 12 (relativo 12 → absoluto 12)
    └── Fardo com 10 caixas (relativo 10 → absoluto 120)
```

Isso atende "unidade, caixa, caixa de atacado" sem caso especial, e deixa o lojista
descrever a embalagem como ele a enxerga: o fardo é definido em caixas, não em unidades.

Conversão é `quantidade × fator_origem ÷ fator_destino`. O fator absoluto é gravado no
momento da escrita, e não calculado a cada leitura, porque ele entra em consulta de saldo.

Unidades de árvores diferentes não convertem: quilo não vira unidade. A tentativa é
recusada em vez de produzir um número.

### 2. Estoque é razão, não coluna de quantidade

O saldo é derivado da soma das movimentações. Não existe campo "quantidade atual" que
alguém possa escrever.

Uma coluna de quantidade mutável é o defeito clássico de sistema de estoque: ela diverge
da realidade e ninguém consegue dizer quando nem por quê. Razão responde "por que o saldo
é esse" — que é a pergunta que o dono faz quando a contagem não bate.

Movimentação é **somente inserção**, como a trilha de auditoria. Correção é lançamento de
ajuste, não edição do passado.

**Limite aceito:** somar a razão fica mais caro conforme ela cresce. Materializar saldo
entra quando for medido, não antes — e o gatilho é o PDV, que tem orçamento de tempo de
resposta. Está registrado aqui para a decisão ser revisitada com número, não com palpite.

### 3. Quantidade é guardada na unidade base do produto

A movimentação registra também a unidade em que foi digitada e o fator usado, para o
documento poder dizer "entraram 10 fardos" enquanto o saldo soma em unidades. Sem isso, a
nota de entrada deixaria de corresponder ao que o fornecedor emitiu.

### 4. Lote e validade são opcionais por produto

Supermercado precisa; ferragista não. O produto declara se controla lote e se controla
validade, e a movimentação exige lote só quando o produto diz que exige.

### 5. O que fica de fora, de propósito

- **Variantes de produto.** O Odoo separa `product.template` de `product.product`, e é uma
  das maiores fontes de complexidade dele. Parafuso 3mm e 4mm podem ser dois produtos
  enquanto ninguém pedir grade de variação.
- **Locais de estoque.** "Separação de produtos" aparece nas anotações, mas sem documento
  que diga o que significa na operação. Acrescentar `location_id` depois é migração de uma
  coluna anulável — barato. Inventar uma hierarquia de locais agora não é.
- **Tabelas de preço.** Produto tem preço de custo e de venda. Regra de preço por cliente,
  quantidade ou período espera requisito real.
- **Compra, venda e PDV.** São módulos sobre esta base, não parte dela.

## Consequências

- O módulo chama-se `comercial` e não depende de nenhuma vertical. As verticais dependem
  dele.
- Cada vertical futura (supermercado, ferragista) tende a ser manifesto + dado-semente +
  poucas telas, que é o que a auditoria do Odoo mostra acontecer lá.
- Dado-semente (unidades e categorias iniciais) continua bloqueado pela lacuna 4.3 do
  benchmark. Até lá o cadastro começa vazio e é preenchido pela tela.
