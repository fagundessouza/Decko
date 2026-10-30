# ADR 0008 — Ponto de venda: o que entra e o que fica de fora

- **Data:** 2026-10-23
- **Status:** aceito

## Contexto

Todos os segmentos pedidos pelo dono do projeto vendem no balcão: supermercado,
lanchonete, restaurante, ferragista, distribuidora. O PDV é o módulo que mais se repete, e
a auditoria do Odoo 20 confirma: a vertical (`pos_restaurant`) é fina porque o peso está
no `point_of_sale`, que por sua vez está sobre produto e estoque.

A base comercial já existe (ADR 0006). O PDV é o primeiro módulo que a consome, e por isso
foi também o que obrigou a decidir a fronteira entre módulos (ADR 0007).

## Decisões

### 1. A venda fecha e o estoque baixa na mesma transação

`finalizar_venda` lança a saída de cada item chamando `comercial.registrar_movimento` e só
então congela o total e grava o status. Tudo no mesmo `BEGIN`.

Não existe estado intermediário em que o cupom saiu e o estoque não baixou. Se o estoque
recusar a saída — produto que exige lote, unidade incompatível — a venda inteira é
desfeita e o caixa vê o motivo.

### 2. Preço e descrição do item são cópia, não referência

O item guarda `preco_unitario` e `descricao` do momento da venda. Remarcar o produto ou
renomeá-lo amanhã não muda o que o cliente pagou hoje, e o cupom reimpresso continua
dizendo o que foi vendido.

É o mesmo princípio da razão de estoque: documento registra o que aconteceu, não o que o
cadastro diz agora.

### 3. O total é calculado no servidor

A resposta de toda operação da venda traz `total`, `pago`, `falta` e `troco` já somados.
A tela não soma dinheiro.

Duas somas do mesmo valor em lugares diferentes divergem — por arredondamento, por ordem
de operação, por um campo que não recarregou — e a que o cliente paga é a do servidor.

### 4. O número da venda só existe ao finalizar

Enquanto aberta, a venda é identificada pelo id. Numerar na abertura gastaria número em
venda abandonada.

O número é reservado por uma linha de contador por empresa, com
`INSERT ... ON CONFLICT DO UPDATE ... RETURNING`: é o banco que serializa dois caixas que
fecham no mesmo instante. Buraco na sequência é possível se a transação for desfeita, e é
aceito — **este número não é número de documento fiscal**, que tem exigência própria.

### 5. Troco só sai de dinheiro

Receber no cartão mais do que a venda e devolver a diferença em espécie transforma o caixa
em saque. A tentativa é recusada.

### 6. Venda finalizada não é cancelada

Cancelar enquanto aberta é só mudar o status: nada foi lançado. Desfazer uma saída de
estoque já lançada é **devolução**, que tem regra própria e consequência fiscal.

Enquanto não houver requisito escrito de um cliente real, a operação é recusada com essa
explicação em vez de inventada — `CLAUDE.md`, regra 6.

## O que fica de fora, de propósito

- **Emissão fiscal (NFC-e, SAT, CF-e).** É o que mais se espera de um PDV brasileiro e é
  justamente o que não pode ser suposto: exige certificado digital, homologação na SEFAZ
  do estado, contingência e layout versionado. Entra como módulo próprio, com requisito
  escrito. Até lá o PDV registra a venda e o estoque, não emite documento fiscal.
- **Abertura e fechamento de caixa** (sangria, suprimento, conferência cega). A regra
  varia por loja e por quem confere. Falta requisito.
- **Bloqueio de venda por saldo insuficiente.** Deixar de vender é decisão comercial do
  dono, não do sistema: supermercado vende com saldo negativo e acerta na contagem. O
  lançamento fica na razão e a divergência aparece; travar por padrão pararia o balcão.
  Vira configuração quando alguém pedir.
- **Cliente na venda, fiado, crediário.** Não há cadastro de cliente na base comercial.
  > **Atualização de 29/10/2026.** A premissa venceu: o módulo `clientes` existe. A
  > **venda identificada** foi feita — ver a seção no fim deste documento. **Fiado e
  > crediário continuam fora**, e não por falta de cadastro: são cobrança a prazo, com
  > limite, vencimento e inadimplência, e nada disso tem requisito escrito.
- **Mesa, comanda e delivery.** São do `pos_restaurant` do Odoo, ou seja: vertical fina
  sobre este módulo. Entram depois, e dependem do dado-semente (lacuna 4.3).
- **Desconto por autorização, cancelamento de item com senha.** Depende de política de
  loja. Hoje quem tem `pdv.venda.write` lança desconto.

## Consequências

- `pdv` declara `depends = ["core", "comercial"]`. Instalar o PDV na vitrine instala a
  base comercial junto.
- O perfil de segmento de comércio passa a ter o que configurar: `comercial` + `pdv`.
- A permissão `pdv.venda.finalizar` é separada de `pdv.venda.write` para que, quando
  houver requisito, o caixa possa lançar sem poder fechar.


---

## Atualização de 29/10/2026 — venda identificada

A lista acima deixava "cliente na venda" de fora por um motivo que deixou de valer: *"não
há cadastro de cliente na base comercial"*. O módulo `clientes` existe, e identificar quem
comprou era uma das razões de ele vir primeiro.

### O PDV passa a depender de `clientes`

`depends = ["core", "comercial", "clientes"]`. Instalar o ponto de venda na vitrine traz o
cadastro de clientes junto, como já traz a base comercial.

**O custo é real e assumido:** a padaria que só quer um caixa ganha um cadastro de clientes
que talvez nunca preencha. A alternativa seria uma porta invertida entre módulos, para o
PDV funcionar com e sem `clientes`. Foi descartada por duas razões. A primeira é que as
portas do projeto são **host ↔ módulo**, e existem porque o host não pode importar módulo
nenhum; acoplamento entre módulos irmãos já tem resposta decidida na ADR 0007, que é
declarar a dependência. A segunda é que "PDV sem cadastro de clientes" é requisito que
ninguém escreveu, e o `CLAUDE.md` veda construir para caso hipotético.

Empresa que já tinha o PDV **sem** `clientes` não recebe o módulo sozinha: instalar na
empresa dos outros sem pedido é o mesmo que a ADR 0010 recusa para a semente. A tela do
PDV simplesmente não oferece identificação enquanto o módulo não estiver ativo, e a
vitrine está ali para quem quiser.

### O que a identificação é, e o que ela não é

`pdv_venda.cliente_id`, nulo por padrão. **Venda anônima continua sendo o caso normal** —
exigir CPF para vender um pão travaria o balcão, e o próprio cadastro de clientes já
admite cliente sem documento pela mesma razão.

Decisões menores, cada uma com o seu motivo:

- **Só enquanto a venda está aberta.** Depois de finalizada tudo nela é congelado — total,
  preço e descrição de cada item — porque o cupom precisa continuar dizendo o que o
  cliente pagou. Trocar a quem a venda pertence depois de fechada seria reescrever um
  documento entregue.
- **A chave estrangeira é `RESTRICT`.** O cadastro de clientes nunca apaga, só desativa,
  justamente para a venda continuar apontando para alguém. O `RESTRICT` é o banco
  cobrando essa promessa.
- **Cliente desativado não pode ser identificado numa venda nova.** Vendas antigas dele
  continuam intactas; desativar quer dizer "não use mais daqui para frente".
- **O nome é lido na hora, não copiado.** Ao contrário do preço e da descrição do item,
  que são cópia. A razão é a diferença entre as duas coisas: o preço de ontem é fato
  histórico e não pode mudar; quem a pessoa é é cadastro, e corrigir um nome digitado
  errado precisa valer para as vendas dela também.

### O que continua fora

**Fiado e crediário.** Identificar quem comprou não é vender a prazo. Cobrança a prazo
exige limite, vencimento, o que acontece quando atrasa e quem autoriza — e nada disso tem
requisito escrito. Está dito aqui para ser decisão, e não esquecimento.
