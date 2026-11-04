# Discovery — o pedido sai do caixa e aparece na cozinha

**Origem:** conversa do dono do projeto com um restaurante do setor dele, relatada em
04/11/2026. **Não houve conversa direta com o cliente ainda**, então o que está aqui é a
dor como foi contada, e as perguntas da seção 4 são para a primeira visita.

## 1. O processo hoje

O cliente paga no caixa e recebe uma **ficha de papel**. Com a ficha na mão, caminha até o
fundo da loja e pede a marmita ao balcão da cozinha.

O resultado é o que o dono do restaurante reclama: **gente acumulada no fundo**. Todo mundo
que pagou vai para o mesmo lugar ao mesmo tempo, e a fila que saiu do caixa se forma de novo
lá atrás, onde não há quem organize.

## 2. O que ele pediu

Nas palavras do dono do projeto:

> *"ele queria uma tela ou impressora lá no fundo no qual ele fecha o pedido no caixa e já
> vai o pedido direto lá pro fundo, assim evita de ficar acumulando muitas pessoas lá."*

Ou seja: fechou a venda no caixa, o pedido **aparece na cozinha** sem ninguém levar papel.

## 3. Por que isto importa mais do que parece

**A dor não é fiscal.** É de operação, como a do agro: ninguém está pedindo cupom, está
pedindo que a fila ande. Isso põe este caso no mesmo lugar estratégico que o módulo agro
ocupa no `NEGOCIO.md` — **vendável sem emissão fiscal**, que é o item mais caro da lista de
bloqueios.

O PDV já registra a venda com itens. O que falta é o pedido **chegar a outro lugar** e ter
um ciclo de vida próprio: recebido, em preparo, pronto, entregue.

## 4. Perguntas em aberto — nada aqui foi suposto

Nenhuma destas foi respondida, e várias mudam o desenho:

1. **Tela ou impressora?** Ele disse "uma tela ou impressora". São produtos diferentes: a
   impressora cospe papel e esquece; a tela guarda estado e precisa ser tocada por alguém
   com a mão suja de comida.
2. **Como o cliente é chamado quando fica pronto?** Hoje a ficha resolve isso: ele está lá.
   Se o pedido vai sozinho para a cozinha, o cliente espera onde, e como sabe que saiu?
   **É a pergunta que decide se a fila realmente deixa de existir** ou só muda de lugar.
3. **O número do pedido é o número da venda?** O PDV já numera por empresa.
4. **Uma cozinha ou várias estações?** Marmita, bebida e sobremesa podem sair de lugares
   diferentes, e aí o pedido se divide.
5. **A cozinha confirma?** Se marcar "pronto" é obrigatório, alguém tem de tocar a tela com
   as mãos ocupadas — e isso costuma ser abandonado na primeira semana.
6. **O que acontece se a tela da cozinha cair** no meio do almoço? A ficha de papel nunca
   cai. Qualquer substituto precisa ser mais confiável que papel, não só mais moderno.
7. **Come no local ou leva?** Muda se existe mesa, comanda e conta aberta — que é outro
   módulo inteiro, não este.
8. **Quantos pedidos no pico?** Dimensiona se isto é uma tela só ou um sistema de filas.

## 5. O que já existe e o que falta

| Peça | Estado |
|---|---|
| Venda com itens, no caixa | **Existe** — módulo `pdv` |
| Numeração por empresa | **Existe** — `pdv_contador` |
| Impressão térmica de recibo | **Existe** — recibo não fiscal |
| Pedido como entidade com estado próprio | **Não existe** |
| Entrega do pedido a outro aparelho | **Não existe** — nada no sistema empurra informação para uma tela que não pediu |
| Tela de cozinha | **Não existe** |

O item que mais pesa é o terceiro: hoje toda tela do Decko **pergunta** ao servidor. Uma
cozinha que espera o pedido aparecer precisa do contrário — o servidor avisando. Isso é
mecanismo novo no sistema, e merece ADR própria quando for a hora.

## 6. Relação com o local-first

A ADR 0019 decidiu que a escrita nasce no aparelho. Aqui isso tem uma consequência boa e uma
ruim, e as duas precisam estar escritas antes de prometer:

- **Boa:** o caixa continua fechando pedido sem rede.
- **Ruim:** se o caixa está offline e a tela da cozinha também, o pedido não atravessa a
  loja. Dois aparelhos na mesma rede local sem internet **não se enxergam** pelo desenho
  atual, que passa tudo pelo servidor.

Para um restaurante no horário de almoço, "o pedido não chegou na cozinha" é pior que
"o sistema está fora do ar": a venda já foi paga.
