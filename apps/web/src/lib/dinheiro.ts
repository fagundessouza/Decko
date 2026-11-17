/* A conta de dinheiro feita no aparelho.
 *
 * Existe porque a venda sem rede não tem a quem perguntar o total. Com rede, quem soma é
 * o servidor e a tela só desenha — é a decisão 3 da `docs/adr/0008-ponto-de-venda.md`, e
 * ela continua valendo. Sem rede a alternativa à conta local é não vender.
 *
 * Tudo aqui é inteiro. `0.1 + 0.2` em ponto flutuante não dá `0.3`, e num caixa isso
 * aparece como um centavo que não fecha no fim do dia — e some quando alguém procura.
 * Então nada de `Number`: os valores viajam como texto decimal e são contados em
 * unidades inteiras da menor casa que cada campo tem.
 *
 * As casas são as do banco, e não uma escolha nova: dinheiro tem 2, quantidade tem 6 e
 * preço unitário tem 4 (`Numeric(18, 2)`, `(18, 6)` e `(18, 4)` em `pdv/models.py`).
 * Divergir daí faria o aparelho mandar um total que o servidor recalcula diferente.
 */

export const CASAS_DINHEIRO = 2;
export const CASAS_QUANTIDADE = 6;
export const CASAS_PRECO = 4;

export class ValorInvalidoError extends Error {}

/** Lê "12,34" ou "12.34" como inteiro na escala pedida. Recusa o que não é número.
 *
 * Vírgula entra porque é o que se digita no balcão. Negativo não entra: nem quantidade,
 * nem preço, nem desconto, nem pagamento aceitam valor negativo do outro lado.
 */
export function escalar(texto: string, casas: number): bigint {
  const limpo = texto.trim().replace(",", ".");
  if (!/^\d+(\.\d*)?$|^\.\d+$/.test(limpo)) {
    throw new ValorInvalidoError(`“${texto}” não é um valor válido.`);
  }

  const [inteira, decimal = ""] = limpo.split(".");
  if (decimal.length > casas) {
    // Cortar em silêncio esconderia o que a pessoa digitou; arredondar aqui seria decidir
    // por ela. Quem digita 1,005 num campo de centavos precisa saber que não cabe.
    throw new ValorInvalidoError(`“${texto}” tem mais casas decimais do que este campo aceita.`);
  }

  return BigInt(inteira || "0") * 10n ** BigInt(casas) + BigInt(decimal.padEnd(casas, "0") || "0");
}

/** Escreve o inteiro de volta como texto decimal, com todas as casas. */
export function escrever(valor: bigint, casas: number): string {
  const unidade = 10n ** BigInt(casas);
  const sinal = valor < 0n ? "-" : "";
  const absoluto = valor < 0n ? -valor : valor;
  const inteira = absoluto / unidade;
  const resto = absoluto % unidade;
  if (casas === 0) return `${sinal}${inteira}`;
  return `${sinal}${inteira}.${resto.toString().padStart(casas, "0")}`;
}

/** Centavos, meio para cima — o mesmo arredondamento do `_dinheiro` do servidor. */
export function aoCentavo(valor: bigint, divisor: bigint): bigint {
  return (valor + divisor / 2n) / divisor;
}

/** O total de uma linha: quantidade × preço, ao centavo, menos o desconto da linha.
 *
 * A ordem importa e é a do servidor (`_dinheiro(quantidade * preco) - _dinheiro(desconto)`):
 * arredondar o produto antes de descontar, e não depois.
 */
export function totalDaLinha(quantidade: bigint, preco: bigint, desconto: bigint): bigint {
  const divisor = 10n ** BigInt(CASAS_QUANTIDADE + CASAS_PRECO - CASAS_DINHEIRO);
  return aoCentavo(quantidade * preco, divisor) - desconto;
}

/** Soma de valores em dinheiro. Existe para a chamada dizer o que ela faz. */
export function somar(valores: bigint[]): bigint {
  return valores.reduce((acumulado, valor) => acumulado + valor, 0n);
}

export function dinheiro(texto: string): bigint {
  return escalar(texto, CASAS_DINHEIRO);
}

export function emReais(centavos: bigint): string {
  return escrever(centavos, CASAS_DINHEIRO);
}
