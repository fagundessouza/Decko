# Identidade visual e regras de interface

## 1. Qual sentimento a interface precisa provocar

Redes de fast-food usam vermelho e amarelo porque o objetivo é fome, urgência e giro rápido de mesa.
**Software de gestão precisa do oposto.** O usuário está olhando dinheiro, estoque, imposto, dado de
cliente e documento com efeito legal. Urgência nesse contexto gera ansiedade e desconfiança.

O gatilho correto é **confiança, controle e calma** — razão pela qual banco, fintech e ERP convergem
historicamente para o azul.

Daí decorre a regra que organiza toda a paleta: **cor aqui tem função semântica, não decorativa.**

## 2. Paleta

| Papel | Cor | Uso | Motivo |
|---|---|---|---|
| Estrutura | Azul-grafite dessaturado | Header, navegação, barra lateral, fundo | Confiança + baixa fadiga visual em turno de 8 horas |
| Ação | Verde | Botão principal, confirmar, sucesso, valores positivos | Precisa **contrastar** com o azul para o CTA não sumir; verde também lê como dinheiro, crescimento e agro |
| Atenção | Âmbar | **Apenas** alerta: validade vencendo, estoque baixo, vento fora da janela | É a cor mais cansativa em tela — nunca em área grande |
| Erro | Vermelho | **Apenas** erro e ação destrutiva: cancelar venda, estorno, exclusão | Se vermelho aparecer por decoração, perde o poder de parar o usuário |
| Leitura | Off-white | Tabelas, relatórios, áreas de dado | Branco puro gera brilho excessivo em jornada longa |

A paleta conversa com a bandeira brasileira, mas a hierarquia é funcional. Amarelo e verde não são
usados por patriotismo — estão lá porque alerta e confirmação precisam dessas cores.

### 2.1 Acento de módulo — identidade, não estado

A tabela acima cobre o que a cor **comunica**. Falta um papel que a vitrine de aplicativos
trouxe: **qual módulo é este**. Com um módulo só, o rótulo bastava. Com uma prateleira de
aplicativos, o olho precisa reconhecer o ponto de venda sem ler.

Cada módulo declara um acento no próprio `module.toml`, pelo nome do papel — nunca pelo
valor:

| Módulo | Acento | |
|---|---|---|
| Ponto de venda | `teal` | azul-esverdeado |
| Produtos e estoque | `blue` | azul |
| Pulverização agrícola | `lime` | verde-limão, a cor do campo |
| Núcleo e configurações | `violet` | violeta |
| Sem acento declarado | `slate` | azul-ardósia |

**O acento não pode virar decoração**, ou a seção 3 cai junto. Três limites o seguram:

1. Nenhum acento é o verde de ação, o âmbar de alerta ou o vermelho de erro. Por isso o
   ponto de venda é azul-esverdeado e não esmeralda: esmeralda **é** o verde do botão, e
   um ícone esmeralda ao lado de "Fechar venda" ensina que verde não quer dizer nada.
2. O acento aparece em dois lugares, e só: a placa do ícone (48px) e o brilho da borda no
   hover. Nunca em botão, texto corrido ou área grande.
3. Ele nunca carrega informação sozinho. O que diz se o módulo está instalado é a etiqueta
   escrita "Instalado", como manda a seção 5.

Os valores estão em `packages/tokens/tokens.css`, e o quanto do acento entra na placa é
token separado da cor (`--dk-tile-wash`), porque no modo escuro o mesmo tom precisa de
mais presença para aparecer.

### 2.2 Ícones

Desenho próprio, não biblioteca de terceiro: são 35 ícones numa folha única, em volume,
na mesma família de azul e grafite da estrutura. Folha, recorte e instruções em
`docs/brand/README.md`.

Cada módulo declara o **nome** do ícone no `module.toml`, nunca o arquivo nem o símbolo —
a arte mora na interface, que resolve o nome. Foi o que permitiu trocar os caracteres
genéricos (`▣`, `✦`, `⊞`) sem tocar em nenhum módulo.

- Dentro da placa de acento: 32px. No menu lateral: 22px.
- O ícone é **decorativo** e sai com `alt` vazio: quem nomeia o módulo é o título ao lado.
  Repetir o nome faria o leitor de tela dizer tudo duas vezes.
- Entra no pacote só o que está em uso. Os 35 juntos passam de 1 MB, e leveza é requisito.
- Nome que a interface ainda não conhece cai num ícone genérico em vez de quebrar a tela.

## 3. Duas descobertas que viraram requisito

**Azul em tudo mata o botão principal.** Se "Finalizar venda" for azul sobre fundo azul, o olho não
encontra o alvo. Por isso o verde é obrigatório como cor de ação, e por isso nenhum elemento
não-acionável pode usar verde.

**Contraste máximo não é melhor.** Quando a Square migrou o PDV para preto-e-branco de alto
contraste, operadores e clientes **idosos** relataram que ficou mais difícil de ler. Como a maior
parte dos donos de loja do público-alvo é idosa, isso vira regra de produto:

- Light mode é o padrão; dark mode é opcional.
- A escolha é **por estação de trabalho**, não imposta pela matriz — o caixa que trabalha no
  corredor claro e o que trabalha no depósito escuro têm necessidades diferentes.
- Nunca preto puro sobre branco puro. `#16202B` sobre `#F6F8FA`.

## 4. Tokens

Fonte única: `packages/tokens/tokens.css`. Nenhum valor de cor é escrito direto em componente.

Se um componente precisa de uma cor que não é token, a pergunta certa é qual função semântica ela
cumpre — não qual tom fica bonito.

## 5. Tipografia e acessibilidade

- Família sem serifa de alta legibilidade (Inter ou equivalente). Sem fonte decorativa.
- Corpo mínimo **16px** na aplicação, **18px** no PDV e no app de campo.
- Área de toque mínima **48px**; no PDV, **64px** — o operador acerta sem olhar.
- Contraste mínimo de texto 4.5:1, verificado em modo claro e escuro.
- Cor nunca é o único portador de informação: alerta e erro sempre acompanham ícone e texto
  (daltonismo, e também tela de PDV desbotada).

## 6. Acabamento

A seção 2 define o que cada cor **significa**. Esta define como a interface **se parece**,
que é coisa diferente — e era o que faltava: semântica correta com acabamento de 2015
continua sendo acabamento de 2015.

Seis decisões respondem por quase toda a diferença:

1. **Tipografia própria, hospedada no projeto.** Inter variável via `@fontsource`, não por
   CDN — o PDV precisa abrir sem internet. Fonte do sistema é o que faz qualquer tela
   parecer um formulário interno.
2. **Título com tracking negativo.** `-0.02em` e peso 650. Uma linha de CSS, e é ela que
   separa "desenhado" de "padrão do navegador".
3. **Neutros com temperatura.** Cinza puro lê como planilha. Os neutros do Decko puxam
   levemente para o azul, acompanhando a cor de estrutura.
4. **Elevação no lugar de borda.** Sombra em duas camadas — uma curta que assenta, outra
   longa e difusa que levanta — em vez de 1px cinza em tudo. No modo escuro a sombra não
   aparece, então lá a profundidade vem de superfície mais clara.
5. **Raio de 12 a 16px.** 8px é a forma de 2015.
6. **Número tabular.** Saldo e coluna de valor usam `font-variant-numeric: tabular-nums`,
   senão a coluna dança a cada dígito.

**Movimento** é para orientar, não enfeitar: entrada de 0,22s, deslocamento de 6px, e
`prefers-reduced-motion` respeitado. Quem usa isto o dia inteiro não quer animação.

**Foco** é anel difuso, não contorno duro: mesma visibilidade para quem navega por
teclado, sem brigar com a estética.

## 7. Responsividade

O alvo é web, celular e desktop com a mesma base de código — e isso **não** é a mesma
tela esticada. Até a primeira versão era: uma barra fina no topo e uma coluna estreita
centralizada, que no computador do caixa deixava a área útil vazia.

- **Até 1024px:** barra superior com gaveta de navegação.
- **A partir de 1024px:** navegação lateral fixa de 256px e conteúdo em grade — duas
  colunas onde o conteúdo justifica, como formulário ao lado do histórico.
- Largura de leitura limitada: formulário estreito, listagem mais larga. Texto corrido
  atravessando 1400px não se lê.

## 8. Padrões de componente

- **Wizard** para cadastro e configuração longos — uma decisão por tela em vez de formulário
  gigante. É isso que permite um operador em campo, no celular, concluir sem treinamento.
- **Modais e submodais** sutis, sem animação chamativa, mantendo o foco na ação atual.
- Estado vazio sempre explica o que fazer em seguida; nunca uma tela em branco.
- Operação destrutiva exige confirmação que diga o que será perdido.

## Referências

Pesquisa que embasou as decisões acima:

- [Color psychology in B2B: stereotypes in web design](https://www.site2b.ua/en/web-blog-en/color-psychology-in-b2b-stereotypes-in-web-design.html) — azul puro reduz a saliência de CTA
- [HubSpot blue website design guide](https://consultevo.com/hubspot-blue-website-design-guide/) — azul como sinal de confiança em B2B/SaaS/financeiro
- [Choosing colors for your dashboard](https://www.thedataschool.co.uk/boglarka-lipka/choosing-colors-for-your-dashboard) — variação sutil para distinguir categoria e ação
- [How does colour psychology affect website design](https://whitehat-seo.co.uk/blog/color-psychology-for-website-design) — contraste baixo é a falha de acessibilidade mais comum
- [Maitre'D Advanced POS UI — Dark Mode](https://docs.maitredpos.com/maitred/maitred-complete-online-documentation/chap-5-configuring-and-managing-work/advanced-pos-workstation/advanced-pos-ui-dark-mode) — modo claro/escuro configurável por estação
- [WCPOS theme settings](https://docs.wcpos.com/settings/store/theme.md) — tema escolhido conforme a iluminação do ambiente
- [Square POS customer display colors](https://community.squareup.com/t5/Orders-Menu-Items-Catalog/POS-Customer-Display-Changed-Colors/m-p/822386) — alto contraste prejudicando usuários idosos

Observação: as fontes acima são majoritariamente material de fornecedor e guias de design, não
estudo controlado. Servem como direção, e as escolhas devem ser validadas com o Nathan e com
operadores reais de caixa.
