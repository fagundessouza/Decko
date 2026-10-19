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

## 6. Padrões de componente

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
