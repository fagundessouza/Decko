# Discovery — periféricos do balcão e pagamento no PDV

**Fonte:** Lucas Fagundes Souza, em 30/10/2026, de memória e a partir da dor de uma cliente
real.
**Status:** requisito colhido. **Nada aqui virou código.** Regra 6 do `CLAUDE.md`: o que não
estiver respondido não é suposto.

---

## 1. A dor, que é o que importa

> *"Uma cliente tinha esse problema: não sabia o que entrava por cartão de crédito e o que
> entrava pelo débito, o que era Pix em qual conta — porque às vezes ela recebia o Pix em
> uma conta ou em outra. Ao final ela tinha que pegar os recibinhos e lançar um a um à
> mão."*

Vale separar a dor do remédio que foi imaginado. **A dor é a conferência de caixa no fim do
expediente**: saber quanto entrou, por qual meio, e em qual conta — sem redigitar.

Conectar na maquininha é **um** caminho para isso, e a seção 4 mostra que não é o único nem
o mais curto.

---

## 2. O que já está resolvido, e talvez não parecesse

| Pedido | Estado |
|---|---|
| **Leitor de código de barras** | **Pronto, e sem integração nenhuma.** Leitor de balcão se apresenta como teclado: digita o código e dá Enter. A tela do PDV mantém o foco no campo o tempo inteiro exatamente por isso — `PdvPage.tsx` |
| **Impressora térmica** | **Pronta**, pela impressora do sistema operacional, em 58 ou 80 mm — ver o recibo não fiscal |
| **Separar crédito, débito, Pix e dinheiro na venda** | **Pronto** no modelo: `FormaPagamento` já distingue, e uma venda aceita vários pagamentos |
| **Velocidade do balcão** | É princípio do projeto desde o começo, e a ADR 0008 decidiu por ele: total vem do servidor, foco nunca sai do campo de código |

**O que falta para a conferência de caixa não é o meio de pagamento** — é saber **em qual
conta** o dinheiro caiu, e o fechamento de caixa, que continua sem requisito escrito no
`ROADMAP.md`.

---

## 3. O que o navegador alcança — e onde ele para

O Decko é aplicação web. Isso decide boa parte do que é possível, e precisa estar escrito
antes de qualquer promessa a cliente.

| Transporte | Navegador | Limite |
|---|---|---|
| **USB "tipo teclado"** (leitor de código de barras) | Todos | Nenhum. Já funciona |
| **Impressora pelo sistema** | Todos | Nenhum. Já funciona |
| **Web Serial** (porta serial, balança) | Chrome, Edge, Opera desde 2021; Firefox só no Nightly desde abr/2026 | **Safari e iOS: não, e a Apple diz que não pretende** |
| **Web Bluetooth / WebUSB / WebHID** | Chromium | **Safari e iOS: não** |

> **A consequência que muda o produto:** no iPhone e no iPad **nenhum** desses caminhos
> existe, porque todo navegador no iOS usa o WebKit. Balança por serial, impressora por
> Bluetooth e maquininha por USB funcionam em PC e Android, e **não** funcionam no aparelho
> da Apple. Prometer "conecta por Bluetooth" sem dizer isso cria um cliente irritado.

O caminho que não tem esse limite é **um agente local** — um programinha que roda na
máquina do caixa e fala com os periféricos, enquanto o navegador fala com ele. O projeto já
tem o veículo previsto para isso na Fase 7 do roadmap: **Tauri**, para empacotar desktop.
Vira decisão de arquitetura, e **precisa de ADR**.

---

## 4. Maquininha de cartão — o pedido e a realidade

> *"Tem que conectar na maquininha por IP ou Bluetooth, não sei, aí entra acho que a IoT né?"*

Não é IoT, e quase nunca é IP ou Bluetooth direto. No Brasil há **três** caminhos, e eles
são muito diferentes em custo e em quem controla o quê:

### 4.1 TEF — a maquininha vira periférico do PDV

O pinpad fica preso ao computador e o PDV manda cobrar. É o caminho mais homologado e o de
menor risco para PDV de terceiro; a própria Stone recomenda a integração por **API
Desktop**. Há soluções de mercado homologadas com Stone, Cielo, PagBank e Rede.

**O preço:** API Desktop quer dizer **agente rodando no Windows** — não é o navegador
falando com a maquininha. Reforça a seção 3.

### 4.2 Smart POS — o PDV roda **dentro** da maquininha

O aplicativo é instalado no terminal Android (Stone, Cielo LIO, PagBank). A Cielo documenta
integração por **deep link** no LIO, dispensando SDK; a mesma página diz que o SDK foi
descontinuado, e tem mais de oito anos — **precisa de confirmação**.

**O preço:** vira outro produto. Um app Android embarcado não é a tela web do Decko, e há
licença por terminal em pelo menos uma das bibliotecas.

### 4.3 API da adquirente, confirmada por webhook

A venda é criada pela API e a confirmação chega ao servidor. **É o único dos três que não
precisa de agente local nem de app embarcado** — e é o que resolve a dor da seção 1 de forma
mais direta, porque a confirmação chega com meio de pagamento e conta identificados.

**O que falta saber:** a busca não achou documentação de webhook de Stone nem de Cielo, e
Sitef e Pay&Go não apareceram. **Precisa de pesquisa dirigida por adquirente** antes de
qualquer decisão.

---

## 5. Pix e o QR code

> *"Se eles selecionarem Pix na máquina e gerar o QR code, quando contabilizar o pagamento
> já registra certinho no meu sistema. Se for máquina que não gera QR code na tela, ele vai
> gerar no monitor do computador ou na tela do celular."*

O desenho está certo, e tem uma peça que falta no Decko hoje: **em qual conta o dinheiro
caiu**. É a metade da dor da cliente, e nada no modelo responde isso — `FormaPagamento.PIX`
diz "foi Pix", não diz para onde foi.

Para Pix dinâmico com confirmação automática é preciso um **PSP** (o banco ou um
intermediário) com API de cobrança e webhook. É **a mesma decisão de gateway** que já está
em aberto no `assinaturas-dois-modulos.md`, pergunta 3 — e agora tem um segundo motivo para
ser tomada.

Enquanto não houver PSP, o honesto é o que o módulo de assinaturas já faz: registrar o
recebimento à mão, com a conta escolhida numa lista.

---

## 6. Balança

Dois mundos, e o segundo já funciona:

- **Balança de balcão por serial/USB** (Toledo, Filizola): protocolo próprio, precisa de
  agente local. Mesmo caminho da seção 3.
- **Balança computadorizada que imprime etiqueta com código de barras**: o leitor lê a
  etiqueta, e o PDV **já trata isso hoje**. O código de barras de pesável carrega o peso
  embutido — e aí é o Decko que precisa saber **interpretar** esse código, que é trabalho de
  software, não de hardware.

**Pergunta:** qual dos dois a distribuidora usa? Bebida raramente é pesável, então pode não
ser necessário nenhum dos dois.

---

## 7. O que precisa de decisão antes de código

**Arquitetura — precisa de ADR**

1. **Vai existir agente local?** É a decisão que destrava serial, Bluetooth e TEF, e a que
   cria um segundo executável para manter, instalar e atualizar na casa do cliente.
2. **Se sim, o Decko vira aplicativo desktop (Tauri, Fase 7) ou um agente pequeno ao lado
   do navegador?** São manutenções muito diferentes.

**Produto**

3. **Qual maquininha?** A resposta muda tudo: TEF, Smart POS e API não se parecem.
4. **O cliente aceita trocar de adquirente** para ter integração? Costuma ser o ponto que
   trava.
5. **iPhone está no alvo?** Se estiver, periférico por Bluetooth/serial está fora para ele.

**Conferência de caixa — a dor de verdade**

6. **Cadastro de contas de recebimento** (qual banco, qual chave Pix) e o pagamento
   apontando para uma. É a peça que falta e que **não depende de hardware nenhum**.
7. **Abertura e fechamento de caixa** continua sem requisito no `ROADMAP.md`, e é o
   relatório que a cliente queria. Quem abre, quem fecha, o que é conferido, sangria e
   suprimento.

---

## 8. A ordem que o material sugere

Opinião, não requisito — e dita porque o pedido mistura coisas de custo muito diferente:

1. **Conta de recebimento no pagamento** + **fechamento de caixa**. Resolve a dor descrita
   (*"não sabia o que entrava por onde"*), é software puro, e não depende de maquininha,
   agente, adquirente nem navegador.
2. **Pix com PSP**, junto da decisão de gateway que já está em aberto.
3. **Agente local e TEF**, com ADR antes — é o item que cria produto novo para manter.

O passo 1 entrega quase toda a dor por quase nenhum custo. Os outros dois são projetos.

---

## 9. Fontes consultadas

Pesquisa de 30/10/2026. Resultados majoritariamente de fornecedores e blogs do setor —
indício, não confirmação.

- [Documentação de TEF da Stone — API Desktop recomendada](https://tefdoc.stone.com.br/docs/getting-started)
- [Cielo LIO — manual de integração](https://developercielo.github.io/manual/cielo-lio)
- [Comparativo de maquininhas e TEF homologado](https://sisfood.com.br/saiba-mais/gestao-financeira/maquininha-cartao-restaurante-comparativo)
- [Web Serial chega ao Firefox Nightly, e a posição da Apple](https://theregister.com/2026/04/14/firefox_nightly_web_serial)
