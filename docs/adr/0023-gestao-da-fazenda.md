# ADR 0023 — Gestão da fazenda: o produtor é outro lado do balcão, e a divisão em módulos

- **Data:** 2026-11-20
- **Status:** aceito para a divisão; **a implementação depende da entrevista** registrada em
  `docs/discovery/agro-gestao-da-fazenda.md`, seção 8
- **Relacionado:** `docs/adr/0005-perfil-de-segmento.md`,
  `docs/adr/0006-base-comercial.md`, `docs/adr/0007-dependencia-entre-modulos.md`

## Contexto

Apareceu um usuário real para gestão rural: a mãe do dono do projeto vai administrar a roça
do avô e pediu um sistema para tocar a propriedade inteira — entrada e saída de produto,
rebanho, vacina, lavoura, máquinas, ferramenta e custo.

O módulo `agro` já existe, mas foi construído para a AgroDrone, que **presta serviço de
pulverização para terceiros**. O modelo diz isso em voz alta: `agro_property` pendura em
`client_id`, e `agro_client` é o contratante do serviço. A fazenda da mãe não cabe ali sem
inventar um cliente que é a própria empresa.

A tentação óbvia — e errada — é ir empurrando tabela para dentro do `agro` até ele virar um
ERP rural. O Odoo tem 696 módulos que se importam em teia e o projeto trata isso como
dívida; repetir o padrão dentro de um módulo só seria a mesma dívida com menos arquivos.

## Decisão 1 — O produtor e o prestador são papéis distintos, e a propriedade muda de dono

`agro_property` deixa de exigir `client_id`. Uma propriedade passa a ser **da empresa** (o
produtor administra a sua fazenda) ou **de um cliente** (o prestador aplica na fazenda do
contratante). O campo fica opcional, e a ausência dele significa "é nossa".

Não se cria uma segunda tabela de propriedade. A fazenda é a mesma coisa nos dois casos —
nome, município, UF, coordenada, talhões. O que muda é de quem ela é, e isso é um campo,
não um modelo.

**Por que não inventar um cliente "a própria empresa":** porque é mentira no modelo, e
mentira no modelo cobra juros. Toda consulta de carteira de clientes passaria a ter de
excluir uma linha especial, e todo relatório de faturamento teria de lembrar disso.

## Decisão 2 — Três módulos novos, e não um nem cinco

| Módulo | O que guarda | `depends` |
|---|---|---|
| `fazenda` | A terra e o ciclo: propriedade própria, talhão, piquete, safra, chuva, plantio, colheita, produtividade | `core`, `comercial` |
| `pecuaria` | O rebanho: categorias, identificação, movimentação, sanidade, pesagem, reprodução | `core`, `fazenda`, `comercial` |
| `frota` | Máquina e implemento: horímetro, odômetro, manutenção, peça, abastecimento | `core`, `comercial` |

E `agro` continua sendo o que é: **a aplicação e a documentação que ela exige** —
receituário, planejamento operacional, clima com registro probatório, relatório do MAPA.

**Por que não um módulo só.** Quem planta soja não quer tela de vacina; quem cria gado não
quer tela de colheita. Módulo é a unidade que o cliente liga e desliga, e um módulo
"fazenda" com tudo dentro obrigaria os dois a carregar o que não usam — que é exatamente o
defeito do pacote fechado que a página de vendas acusa no concorrente.

**Por que não cinco.** A divisão mais fina seria separar `lavoura` de `fazenda`. Hoje não
há o que a separe: talhão, safra e colheita são o mesmo ciclo, e dividir agora seria criar
abstração para caso hipotético, contra a regra do `CLAUDE.md`. Se a lavoura crescer a ponto
de ter vida própria — rotação, zoneamento, agricultura de precisão — ela sai de dentro, e
aí a divisão terá sido ganha.

**Por que `frota` não depende de `fazenda`.** Caminhão não é coisa de fazenda: a
distribuidora de bebidas precisa de frota e a página dela já admite que romaneio e acerto
de rota não existem. Prender frota à fazenda fecharia essa porta por nada.

## Decisão 3 — O estoque da fazenda é o `comercial`, sem motor novo

Soja no silo, semente, adubo, defensivo, vacina, peça de trator e diesel no tanque são
todos **estoque**: produto, unidade, lote, validade, saldo que é a soma do que entrou e
saiu. O `comercial` já faz isso, e refazê-lo dentro de `fazenda` seria a duplicação que o
ADR 0006 existe para impedir.

O que falta no `comercial` não é um motor, é **um motivo de movimentação**: hoje a saída é
venda, e na fazenda a saída principal é **consumo interno** — o adubo que foi para o talhão
7, o diesel que foi para o trator, a vacina que foi para o lote de bezerros.

Daí sai a terceira peça: todo consumo interno aponta para **contra o quê** foi consumido —
um talhão, um lote de gado, uma máquina. É isso, e só isso, que permite responder quanto
custou o hectare e quanto custou a arroba. Sem esse apontamento, o sistema registra bem e
não responde nada.

## Decisão 4 — As duplicações de hoje se resolvem antes de crescer

Três já existem no repositório e vão piorar com a fazenda dentro:

1. **`agro_client` × `clientes.cliente`.** O `agro` nasceu antes do módulo `clientes`. A
   dívida se paga fazendo `agro` depender de `clientes` e apagar a tabela dele — migração
   de dado, não só de schema.
2. **`agro_product` × `comercial.produto`.** O defensivo precisa de classe toxicológica e
   registro no MAPA (que são do `agro`) e de saldo, lote e embalagem (que são do
   `comercial`). O caminho é o `agro_product` virar **extensão** do produto do comercial,
   apontando para ele, em vez de ser outro cadastro.
3. **`agro_aircraft` como única máquina.** `prefixo` é matrícula de aeronave; autopropelido
   e trator não têm. A máquina vira cadastro do `frota`, e o que é de aeronave — prefixo,
   e o piloto com CANAC — fica como extensão no `agro`, pelo mesmo padrão do item 2.

Nenhuma das três entra na primeira fatia. Estão aqui porque **a ordem importa**: fazer a
fazenda por cima das duplicações multiplica o custo de desfazê-las depois.

## Decisão 5 — O ramo ativa os módulos, pelo mecanismo que já existe

O pedido de "quando a empresa mostrar que é do agro, os módulos do agro ativam, igual no
Odoo" já é o que o perfil de segmento faz (ADR 0005). O que faltava era o perfil:
`profiles/produtor-rural.toml` entra agora com o que existe —
`clientes`, `comercial`, `compras`, `financeiro`, `agro` — e cresce quando cada módulo
nascer.

São **dois perfis para o agro**, e é de propósito: `pulverizacao-agricola` é o prestador de
serviço, `produtor-rural` é o dono da terra. Mesmo setor, operações opostas, e o perfil é
justamente o atalho entre o ramo e os módulos.

## Consequências

**Boas**
- Três buracos do Decko inteiro ganham dono: contas a pagar, centro de custo e frota.
- O segundo módulo do projeto com usuário real do lado, como foi a pulverização.
- Nenhum motor novo de estoque, de permissão ou de auditoria: tudo reaproveita.

**Ruins, e assumidas**
- O `agro` vai ter de ser mexido, e ele já está em produção numa operação real. Toda
  mudança nele carrega risco que a fazenda não carregaria sozinha.
- `financeiro` precisa crescer para contas a pagar antes de a fazenda fazer sentido
  econômico, e isso não é fatia pequena.
- Três módulos novos é muita superfície de uma vez. A ordem de entrega está no roadmap, e
  nenhuma fatia começa antes das respostas da entrevista.

**O que invalidaria esta decisão**
- Se a entrevista mostrar que a mãe não controla gado, `pecuaria` não nasce e `fazenda`
  absorve o resto.
- Se ela não tiver máquina própria, `frota` espera a distribuidora pedir.
