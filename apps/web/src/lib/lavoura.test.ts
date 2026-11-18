import "fake-indexeddb/auto";

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError, SemRedeError } from "./api";
import type { PlanoNovo } from "./lavoura";

/* O planejamento operacional preenchido na lavoura.
 *
 * Fatia 6 da `docs/adr/0022-offline-first-as-respostas.md`, a terceira das três telas que
 * a resposta 5 põe no escopo — e a que o piloto usa onde não há sinal. O planejamento é o
 * talão de papel que o Nathan leva a campo e depois passa para a planilha.
 *
 * O que se afirma aqui: o formulário tem com que ser preenchido sem rede, o planejamento
 * não se perde, e ele sobe **uma vez** — número de planejamento é o que o produtor recebe
 * no documento, e dois números para o mesmo voo é defeito que chega ao cliente.
 */

vi.mock("./agro", async (original) => ({
  ...(await original<typeof import("./agro")>()),
  agro: {
    listPlans: vi.fn(),
    listClients: vi.fn(),
    listProperties: vi.fn(),
    createPlan: vi.fn(),
  },
}));

const { agro } = await import("./agro");
const lavoura = await import("./lavoura");
const { enviarPendentes } = await import("./sincronia");
const local = await import("./local");

const EMPRESA = "pulverizacao-do-teste";

const CONTRATANTE = { id: "contratante-1", nome: "Fazenda Santa Clara", cpf_cnpj: "12345678000195" };
const PROPRIEDADE = {
  id: "propriedade-1",
  client_id: "contratante-1",
  nome: "Talhão Norte",
  municipio: "Jataí",
  uf: "GO",
  latitude: null,
  longitude: null,
};

function umPlano(sobre: Record<string, unknown> = {}) {
  return {
    id: "plano-do-servidor",
    numero: 7,
    status: "rascunho",
    client_id: CONTRATANTE.id,
    property_id: PROPRIEDADE.id,
    prescription_id: null,
    data_aplicacao: "2026-11-17",
    cultura: "soja",
    area_ha: "120.5",
    param_temperatura_maxima_c: "30",
    param_umidade_relativa_min_pct: "50",
    param_velocidade_vento_max_kmh: "10",
    ...sobre,
  } as never;
}

function corpoNovo(sobre: Partial<PlanoNovo> = {}): PlanoNovo {
  return {
    client_id: CONTRATANTE.id,
    property_id: PROPRIEDADE.id,
    data_aplicacao: "2026-11-17",
    cultura: "milho",
    cultura_outras_texto: null,
    area_ha: 42.5,
    param_velocidade_vento_max_kmh: 10,
    param_temperatura_maxima_c: 30,
    param_umidade_relativa_min_pct: 50,
    ...sobre,
  };
}

beforeEach(async () => {
  vi.clearAllMocks();
  local.fechar();
  for (const armazem of ["fila", "planos", "contratantes", "propriedades"] as const) {
    await local.esvaziar(EMPRESA, armazem);
  }
});

afterEach(() => local.fechar());

// ------------------------------------------------------- o que o formulário precisa ter

it("com rede, guarda contratantes e propriedades para depois", async () => {
  vi.mocked(agro.listClients).mockResolvedValue([CONTRATANTE] as never);
  vi.mocked(agro.listProperties).mockResolvedValue([PROPRIEDADE] as never);

  const primeira = await lavoura.cadastros(EMPRESA);
  expect(primeira.doCache).toBe(false);

  // Agora sem rede: o formulário continua com o que preencher.
  vi.mocked(agro.listClients).mockRejectedValue(new SemRedeError());
  vi.mocked(agro.listProperties).mockRejectedValue(new SemRedeError());

  const segunda = await lavoura.cadastros(EMPRESA);
  expect(segunda.doCache).toBe(true);
  expect(segunda.contratantes[0].nome).toBe("Fazenda Santa Clara");
  expect(segunda.propriedades[0].nome).toBe("Talhão Norte");
});

it("sem nada guardado e sem rede, devolve vazio em vez de quebrar a tela", async () => {
  /* Aparelho que nunca abriu a tela com rede não tem o que oferecer — mas quebrar o
   * formulário seria pior: o piloto não saberia por que nada aparece. */
  vi.mocked(agro.listClients).mockRejectedValue(new SemRedeError());
  vi.mocked(agro.listProperties).mockRejectedValue(new SemRedeError());

  const vista = await lavoura.cadastros(EMPRESA);

  expect(vista.contratantes).toEqual([]);
  expect(vista.doCache).toBe(true);
});

// ------------------------------------------------------- criar o planejamento

it("com rede, o planejamento vai direto e já volta com número", async () => {
  vi.mocked(agro.createPlan).mockResolvedValue(umPlano());

  const { plano, pendente } = await lavoura.salvarPlano(EMPRESA, corpoNovo());

  expect(pendente).toBe(false);
  expect(plano.numero).toBe(7);
  // A identidade vai daqui mesmo com rede: é ela que torna o reenvio inofensivo.
  const corpo = vi.mocked(agro.createPlan).mock.calls[0][0] as { id?: string };
  expect(corpo.id).toMatch(/^[0-9a-f-]{36}$/);

  // Nada na fila: o que entrou no servidor não precisa ser lembrado aqui.
  vi.mocked(agro.listPlans).mockResolvedValue([umPlano()] as never);
  expect((await lavoura.listarPlanos(EMPRESA)).pendentes.size).toBe(0);
});

it("sem rede, o planejamento fica guardado e a tela segue", async () => {
  vi.mocked(agro.createPlan).mockRejectedValue(new SemRedeError());
  vi.mocked(agro.listPlans).mockRejectedValue(new SemRedeError());

  const { plano, pendente } = await lavoura.salvarPlano(EMPRESA, corpoNovo());

  expect(pendente).toBe(true);
  // Sem número: ele é do servidor, e dois aparelhos sem rede não combinam um contador.
  expect(plano.numero).toBeNull();
  expect(plano.cultura).toBe("milho");

  // E ele aparece na lista, marcado — senão o piloto preencheria tudo de novo.
  const visao = await lavoura.listarPlanos(EMPRESA);
  expect(visao.planos.map((p) => p.id)).toContain(plano.id);
  expect(visao.pendentes.has(plano.id)).toBe(true);
  expect(visao.doCache).toBe(true);
});

it("o planejamento guardado sobe quando a rede volta, e sai da fila", async () => {
  vi.mocked(agro.createPlan).mockRejectedValue(new SemRedeError());
  const { plano } = await lavoura.salvarPlano(EMPRESA, corpoNovo());

  vi.mocked(agro.createPlan).mockResolvedValue(umPlano({ id: plano.id, numero: 8 }));
  const resultado = await enviarPendentes(EMPRESA);

  expect(resultado.enviados).toBe(1);
  const corpo = vi.mocked(agro.createPlan).mock.calls.at(-1)?.[0] as {
    id: string;
    cultura: string;
    area_ha: number;
  };
  expect(corpo.id).toBe(plano.id);
  expect(corpo.cultura).toBe("milho");
  expect(corpo.area_ha).toBe(42.5);

  vi.mocked(agro.listPlans).mockResolvedValue([umPlano({ id: plano.id, numero: 8 })] as never);
  const visao = await lavoura.listarPlanos(EMPRESA);
  expect(visao.pendentes.size).toBe(0);
  expect(visao.planos[0].numero).toBe(8);
});

it("o planejamento recusado pelo servidor fica com o motivo à vista", async () => {
  /* Tentar de novo não resolveria, e apagar esconderia do piloto que o documento dele não
   * entrou. A divergência tem de aparecer — ADR 0022. */
  vi.mocked(agro.createPlan).mockRejectedValue(new SemRedeError());
  const { plano } = await lavoura.salvarPlano(EMPRESA, corpoNovo());

  vi.mocked(agro.createPlan).mockRejectedValue(
    new ApiError("Contratante, propriedade, aeronave ou receituário não encontrados.", 409),
  );
  await enviarPendentes(EMPRESA);

  vi.mocked(agro.listPlans).mockRejectedValue(new SemRedeError());
  const visao = await lavoura.listarPlanos(EMPRESA);
  expect(visao.recusados.get(plano.id)).toContain("não encontrados");
  // Continua na tela: ele não pode sumir sem alguém ver.
  expect(visao.planos.map((p) => p.id)).toContain(plano.id);
});

it("dois planejamentos sem rede são dois, e não um", async () => {
  // A chave da fila é a identidade do planejamento; dois voos são duas identidades.
  vi.mocked(agro.createPlan).mockRejectedValue(new SemRedeError());
  vi.mocked(agro.listPlans).mockRejectedValue(new SemRedeError());

  await lavoura.salvarPlano(EMPRESA, corpoNovo({ cultura: "milho" }));
  await lavoura.salvarPlano(EMPRESA, corpoNovo({ cultura: "soja" }));

  const visao = await lavoura.listarPlanos(EMPRESA);
  expect(visao.pendentes.size).toBe(2);
});

it("a lista guardada não mistura o planejamento de outra empresa", async () => {
  /* O isolamento no servidor é do PostgreSQL; no aparelho é o nome do banco. Duas
   * empresas no mesmo tablet não podem ver o voo uma da outra. */
  vi.mocked(agro.listPlans).mockResolvedValue([umPlano()] as never);
  await lavoura.listarPlanos(EMPRESA);

  vi.mocked(agro.listPlans).mockRejectedValue(new SemRedeError());
  const daOutra = await lavoura.listarPlanos("outra-empresa");

  expect(daOutra.planos).toEqual([]);
});
