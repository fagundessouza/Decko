import { afterEach, describe, expect, it, vi } from "vitest";

import { brl, dateBr, cestMask, ncmMask, num, periodoOfNow, todayLocal, ventoBr } from "./format";

/* As funções de formatação.
 *
 * Parecem o tipo de código que não precisa de teste, e são justamente onde dois defeitos
 * nasceram: a leitura meteorológica mostrava "0° (N)" quando não havia direção de vento,
 * e a data saía do dia seguinte depois das 21h. Nenhum dos dois é erro de tipo, então
 * nem `oxlint` nem `tsc` tinham como ver.
 *
 * A suíte roda em `America/Sao_Paulo`, fixado em `vite.config.ts`. Sem isso o teste de
 * data passaria por engano na esteira, que roda em UTC: o defeito que ele guarda só
 * aparece quando o fuso local difere do UTC. */

afterEach(() => {
  vi.useRealTimers();
});

describe("ventoBr", () => {
  it("mostra grau e rumo", () => {
    expect(ventoBr(135)).toBe("135° (SE)");
    expect(ventoBr("0")).toBe("0° (N)");
    expect(ventoBr(360)).toBe("360° (N)");
  });

  it("não inventa norte quando não há leitura", () => {
    // Era o defeito: `Number(null)` é 0, e zero grau é norte, então ausência de direção
    // saía impressa como "0° (N)" — dado inventado num documento com função probatória.
    expect(ventoBr(null)).toBe("—");
    expect(ventoBr(undefined)).toBe("—");
    expect(ventoBr("")).toBe("—");
    expect(ventoBr("sei lá")).toBe("—");
  });
});

describe("todayLocal", () => {
  it("usa o dia de quem está no campo, e não o de Greenwich", () => {
    // 3 de novembro, 22h30 em São Paulo, já é dia 4 em UTC. `toISOString()` devolveria
    // "2026-11-04" e o documento sairia com a data errada — justamente nos registros de
    // fim de turno, que é quando o relatório é preenchido.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-03T22:30:00-03:00"));

    expect(todayLocal()).toBe("2026-11-03");
    expect(new Date().toISOString().slice(0, 10)).toBe("2026-11-04");
  });

  it("preenche mês e dia com dois dígitos", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-05T10:00:00-03:00"));

    expect(todayLocal()).toBe("2026-01-05");
  });
});

describe("periodoOfNow", () => {
  it("vira vespertino ao meio-dia", () => {
    vi.useFakeTimers();

    vi.setSystemTime(new Date("2026-11-03T11:59:00-03:00"));
    expect(periodoOfNow()).toBe("matutino");

    vi.setSystemTime(new Date("2026-11-03T12:00:00-03:00"));
    expect(periodoOfNow()).toBe("vespertino");
  });
});

describe("brl", () => {
  it("não esconde centavo", () => {
    // `toLocaleString` usa espaço estreito sem quebra entre "R$" e o número, e não o
    // espaço comum. Comparar com "R$ 120,50" digitado à mão falharia por isso.
    expect(brl("120.5")).toBe((120.5).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
    expect(brl("120.5")).toMatch(/^R\$.120,50$/);
    expect(brl(0)).toMatch(/^R\$.0,00$/);
  });

  it("vira zero diante de valor ausente ou ilegível", () => {
    // Dinheiro não mostra "—" nem "NaN" na tela do caixa: mostra zero.
    expect(brl(null)).toMatch(/^R\$.0,00$/);
    expect(brl(undefined)).toMatch(/^R\$.0,00$/);
    expect(brl("abacaxi")).toMatch(/^R\$.0,00$/);
  });
});

describe("num", () => {
  it("usa vírgula decimal e corta o zero à direita", () => {
    expect(num("1.5")).toBe("1,5");
    expect(num("2.0")).toBe("2");
    expect(num(3)).toBe("3");
  });

  it("respeita o número de casas pedido", () => {
    expect(num("1.567", 2)).toBe("1,57");
  });

  it("diz travessão quando não há valor", () => {
    expect(num(null)).toBe("—");
    expect(num("")).toBe("—");
    expect(num("abacaxi")).toBe("—");
  });
});

describe("dateBr", () => {
  it("inverte a data sem passar por Date", () => {
    // Converter para Date e de volta desloca o dia conforme o fuso; a troca de posição
    // não tem como errar.
    expect(dateBr("2026-11-03")).toBe("03/11/2026");
    expect(dateBr(null)).toBe("—");
  });
});

describe("máscaras fiscais", () => {
  it("pontua o NCM como se lê no edital", () => {
    expect(ncmMask("3808")).toBe("3808");
    expect(ncmMask("380893")).toBe("3808.93");
    expect(ncmMask("38089329")).toBe("3808.93.29");
  });

  it("recusa o nono dígito do NCM e ignora o que não é número", () => {
    expect(ncmMask("380893291")).toBe("3808.93.29");
    expect(ncmMask("3808.93.29")).toBe("3808.93.29");
  });

  it("pontua o CEST", () => {
    expect(cestMask("01")).toBe("01");
    expect(cestMask("0100100")).toBe("01.001.00");
    expect(cestMask("01001001")).toBe("01.001.00");
  });
});
