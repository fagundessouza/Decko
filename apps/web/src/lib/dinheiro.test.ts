import { expect, it } from "vitest";

import {
  CASAS_PRECO,
  CASAS_QUANTIDADE,
  dinheiro,
  emReais,
  escalar,
  escrever,
  somar,
  totalDaLinha,
  ValorInvalidoError,
} from "./dinheiro";

/* A conta de dinheiro feita no aparelho.
 *
 * Com rede, quem soma é o servidor. Sem rede não há a quem perguntar, e a alternativa à
 * conta local é não vender — por isso ela existe, e por isso ela precisa dar o **mesmo**
 * resultado que o `Decimal` do Python dá do outro lado.
 *
 * O que estes testes afirmam é a aritmética, e não a tela: um centavo de diferença não
 * aparece na venda, aparece no fechamento do caixa, horas depois, quando ninguém mais
 * sabe de qual venda ele veio.
 */

it("soma de centavos não escorrega como ponto flutuante", () => {
  // `0.1 + 0.2 !== 0.3` em `Number`. Aqui são inteiros, e 10 + 20 é 30.
  expect(emReais(somar([dinheiro("0.10"), dinheiro("0.20")]))).toBe("0.30");

  // O caso clássico do caixa: dez itens de R$ 0,07.
  const dez = somar(Array.from({ length: 10 }, () => dinheiro("0.07")));
  expect(emReais(dez)).toBe("0.70");
});

it("cento e vinte itens de centavo fecham em um real e vinte", () => {
  const centavos = somar(Array.from({ length: 120 }, () => dinheiro("0.01")));
  expect(emReais(centavos)).toBe("1.20");
});

it("a vírgula do balcão vale tanto quanto o ponto", () => {
  // Quem está no caixa digita "19,90". Recusar isso seria recusar o teclado da pessoa.
  expect(dinheiro("19,90")).toBe(dinheiro("19.90"));
});

it("o que não é número é recusado, em vez de virar zero", () => {
  // Virar zero é o defeito que só aparece no fechamento: a venda sai de graça.
  expect(() => dinheiro("abc")).toThrow(ValorInvalidoError);
  expect(() => dinheiro("")).toThrow(ValorInvalidoError);
  expect(() => dinheiro("-5.00")).toThrow(ValorInvalidoError);
  expect(() => dinheiro("1.2.3")).toThrow(ValorInvalidoError);
});

it("mais casas do que o campo aceita é recusado, e não arredondado em silêncio", () => {
  // Arredondar aqui seria decidir pela pessoa o que ela quis dizer com "1,005".
  expect(() => dinheiro("1.005")).toThrow(ValorInvalidoError);
  expect(escalar("1.005", CASAS_PRECO)).toBe(10050n);
});

it("o total da linha arredonda ao centavo, meio para cima — como o servidor", () => {
  // 3 × R$ 0,335 = R$ 1,005. Meio para cima dá 1,01; truncar daria 1,00.
  const quantidade = escalar("3", CASAS_QUANTIDADE);
  const preco = escalar("0.335", CASAS_PRECO);
  expect(emReais(totalDaLinha(quantidade, preco, 0n))).toBe("1.01");
});

it("quantidade fracionada vale, que é como se vende carne e grão", () => {
  // 1,250 kg × R$ 42,90 = R$ 53,625 → R$ 53,63.
  const quantidade = escalar("1,250", CASAS_QUANTIDADE);
  const preco = escalar("42.90", CASAS_PRECO);
  expect(emReais(totalDaLinha(quantidade, preco, 0n))).toBe("53.63");
});

it("o desconto da linha sai depois do arredondamento, na ordem do servidor", () => {
  /* O servidor faz `_dinheiro(quantidade * preco) - _dinheiro(desconto)`. Descontar antes
   * de arredondar dá um centavo de diferença justamente nos casos de meio centavo. */
  const quantidade = escalar("3", CASAS_QUANTIDADE);
  const preco = escalar("0.335", CASAS_PRECO);
  expect(emReais(totalDaLinha(quantidade, preco, dinheiro("0.01")))).toBe("1.00");
});

it("escreve de volta com todas as casas, como o banco devolve", () => {
  // A tela e o servidor esperam texto decimal com as casas da coluna.
  expect(escrever(escalar("2", CASAS_QUANTIDADE), CASAS_QUANTIDADE)).toBe("2.000000");
  expect(escrever(escalar("19.9", CASAS_PRECO), CASAS_PRECO)).toBe("19.9000");
  expect(emReais(0n)).toBe("0.00");
});
