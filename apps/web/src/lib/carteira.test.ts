import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, SemRedeError } from "./api";

/* A carteira de clientes sem rede.
 *
 * Fatia 2 da `docs/adr/0022-offline-first-as-respostas.md`. O que estes testes guardam é
 * a frase do dono do projeto que originou tudo: *"tem que manter a operação, não pode
 * morrer ou travar ou parar"*.
 *
 * Então: cadastrar sem rede funciona, o cadastro continua na tela depois de recarregar,
 * sobe sozinho quando a rede volta — e o que o servidor recusar **aparece**, em vez de
 * sumir da fila fingindo que entrou.
 */

vi.mock("./clientes", async (original) => ({
  ...(await original<typeof import("./clientes")>()),
  clientes: { listar: vi.fn(), criar: vi.fn(), atualizar: vi.fn() },
}));

const { clientes } = await import("./clientes");
const { listar, salvar } = await import("./carteira");
// Quem esvazia a fila agora é `sincronia`: ela guarda cadastro e venda juntos, e a rota
// por ação vive lá — ver `apps/web/src/lib/sincronia.ts`.
const { enviarPendentes } = await import("./sincronia");
const { pendentes } = await import("./fila");
const local = await import("./local");

const EMPRESA = "loja-de-teste";

const CORPO = {
  tipo: "fisica" as const,
  nome: "Maria do Campo",
  cpf_cnpj: "12345678909",
};

function umCliente(sobre: Partial<Record<string, unknown>> = {}) {
  return {
    id: "c-servidor",
    tipo: "fisica",
    nome: "Já cadastrado",
    apelido: null,
    tenant_assinante_id: null,
    cpf_cnpj: null,
    inscricao_estadual: null,
    email: null,
    telefone: null,
    cep: null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: null,
    cidade: null,
    uf: null,
    observacao: null,
    ativo: true,
    ...sobre,
  } as never;
}

beforeEach(async () => {
  vi.clearAllMocks();
  local.fechar();
  await local.esvaziar(EMPRESA, "fila");
  await local.esvaziar(EMPRESA, "clientes");
});

afterEach(() => {
  local.fechar();
});

describe("com rede", () => {
  it("salva direto no servidor e não enfileira nada", async () => {
    vi.mocked(clientes.criar).mockResolvedValue(umCliente({ id: "c-1", nome: CORPO.nome }));

    const salvo = await salvar(EMPRESA, CORPO);

    expect(salvo.pendente).toBe(false);
    expect(clientes.criar).toHaveBeenCalled();
    expect(await pendentes(EMPRESA)).toHaveLength(0);
  });

  it("manda a identidade junto, para o reenvio não duplicar do outro lado", async () => {
    vi.mocked(clientes.criar).mockResolvedValue(umCliente());

    await salvar(EMPRESA, CORPO);

    const enviado = vi.mocked(clientes.criar).mock.calls[0][0];
    expect(enviado.id).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("sem rede", () => {
  beforeEach(() => {
    vi.mocked(clientes.criar).mockRejectedValue(new SemRedeError());
    vi.mocked(clientes.atualizar).mockRejectedValue(new SemRedeError());
    vi.mocked(clientes.listar).mockRejectedValue(new SemRedeError());
  });

  it("o cadastro acontece mesmo assim, e vai para a fila", async () => {
    const salvo = await salvar(EMPRESA, CORPO);

    expect(salvo.pendente).toBe(true);
    expect(salvo.cliente.nome).toBe("Maria do Campo");

    const fila = await pendentes(EMPRESA);
    expect(fila).toHaveLength(1);
    expect(fila[0].acao).toBe("cliente.criar");
  });

  it("o que foi cadastrado sem rede continua na lista depois de recarregar", async () => {
    /* Sem isto, a pessoa digitaria tudo de novo — e, quando a fila subisse, teríamos dois
     * cadastros do mesmo cliente. */
    await salvar(EMPRESA, CORPO);

    const visao = await listar(EMPRESA);

    expect(visao.doCache).toBe(true);
    expect(visao.clientes.map((c) => c.nome)).toContain("Maria do Campo");
    expect(visao.pendentes.size).toBe(1);
  });

  it("com a rede de volta, o pendente não some da lista antes de subir", async () => {
    /* A rede volta, a lista do servidor carrega, e a fila ainda não esvaziou. Sem
     * sobrepor, o cadastro feito no campo desapareceria da tela por alguns segundos — e
     * quem olhasse nessa hora digitaria tudo de novo. */
    await salvar(EMPRESA, CORPO);
    vi.mocked(clientes.listar).mockResolvedValue([umCliente({ nome: "Do servidor" })]);

    const visao = await listar(EMPRESA, undefined, true);

    expect(visao.doCache).toBe(false);
    expect(visao.clientes.map((c) => c.nome)).toContain("Maria do Campo");
    expect(visao.clientes.map((c) => c.nome)).toContain("Do servidor");
    expect(visao.pendentes.size).toBe(1);
  });

  it("a lista cai no que o aparelho guardou da última vez com rede", async () => {
    await local.gravar(EMPRESA, "clientes", umCliente({ id: "c-antigo", nome: "Do cache" }));

    const visao = await listar(EMPRESA);

    expect(visao.doCache).toBe(true);
    expect(visao.clientes.map((c) => c.nome)).toContain("Do cache");
  });

  it("duas edições do mesmo cliente viram um item só na fila", async () => {
    const existente = umCliente({ id: "c-9", nome: "Primeiro nome" }) as never as {
      id: string;
      nome: string;
    };
    await salvar(EMPRESA, { ...CORPO, nome: "Segundo nome" }, existente as never);
    await salvar(EMPRESA, { ...CORPO, nome: "Terceiro nome" }, existente as never);

    const fila = await pendentes(EMPRESA);
    expect(fila).toHaveLength(1);
    expect((fila[0].corpo as { nome: string }).nome).toBe("Terceiro nome");
  });
});

describe("quando a rede volta", () => {
  it("a fila sobe e some", async () => {
    vi.mocked(clientes.criar).mockRejectedValueOnce(new SemRedeError());
    await salvar(EMPRESA, CORPO);
    expect(await pendentes(EMPRESA)).toHaveLength(1);

    vi.mocked(clientes.criar).mockResolvedValue(umCliente({ id: "c-1" }));
    const resultado = await enviarPendentes(EMPRESA);

    expect(resultado).toMatchObject({ enviados: 1, recusados: 0, semRede: false });
    expect(await pendentes(EMPRESA)).toHaveLength(0);
  });

  it("o que o servidor recusa fica na fila, com o motivo", async () => {
    /* Apagar seria esconder da pessoa que o cadastro dela não entrou. A divergência é o
     * produto — ADR 0022. */
    vi.mocked(clientes.criar).mockRejectedValueOnce(new SemRedeError());
    await salvar(EMPRESA, CORPO);

    vi.mocked(clientes.criar).mockRejectedValue(
      new ApiError("Já existe um cliente com este CPF ou CNPJ.", 422),
    );
    const resultado = await enviarPendentes(EMPRESA);

    expect(resultado).toMatchObject({ enviados: 0, recusados: 1 });
    const fila = await pendentes(EMPRESA);
    expect(fila).toHaveLength(1);
    expect(fila[0].erro).toContain("CPF");
  });

  it("item já recusado não é tentado de novo sozinho", async () => {
    vi.mocked(clientes.criar).mockRejectedValueOnce(new SemRedeError());
    await salvar(EMPRESA, CORPO);
    vi.mocked(clientes.criar).mockRejectedValue(new ApiError("recusado", 422));
    await enviarPendentes(EMPRESA);

    vi.mocked(clientes.criar).mockClear();
    const segunda = await enviarPendentes(EMPRESA);

    expect(clientes.criar).not.toHaveBeenCalled();
    expect(segunda).toMatchObject({ enviados: 0, recusados: 0 });
  });

  it("se a rede cair no meio, para ali e guarda todo o resto", async () => {
    /* Três itens, e não dois: com dois, parar na queda e seguir em frente dão o mesmo
     * resultado, e o teste não veria diferença. O terceiro é que mostra se a fila parou
     * ou se continuou gastando tentativa contra uma rede que não está lá. */
    vi.mocked(clientes.criar).mockRejectedValue(new SemRedeError());
    await salvar(EMPRESA, { ...CORPO, nome: "Primeiro" });
    await new Promise((pronto) => setTimeout(pronto, 2));
    await salvar(EMPRESA, { ...CORPO, nome: "Segundo" });
    await new Promise((pronto) => setTimeout(pronto, 2));
    await salvar(EMPRESA, { ...CORPO, nome: "Terceiro" });
    expect(await pendentes(EMPRESA)).toHaveLength(3);

    vi.mocked(clientes.criar)
      .mockResolvedValueOnce(umCliente({ id: "c-1" }))
      .mockRejectedValueOnce(new SemRedeError())
      .mockResolvedValueOnce(umCliente({ id: "c-3" }));
    const resultado = await enviarPendentes(EMPRESA);

    expect(resultado).toMatchObject({ enviados: 1, semRede: true });
    // O segundo **e o terceiro** continuam na fila: a rede caiu no segundo.
    expect(await pendentes(EMPRESA)).toHaveLength(2);
  });
});

describe("sem armazenamento no aparelho", () => {
  /* Janela anônima, site bloqueado, cota estourada. Quem está com rede não pode perder a
   * tela por causa disso: sem o aparelho, o Decko volta a ser o que era, e isso funciona. */
  it("a lista continua vindo do servidor", async () => {
    vi.spyOn(local, "lerTodos").mockRejectedValue(new local.LocalIndisponivelError());
    vi.spyOn(local, "gravarVarios").mockRejectedValue(new local.LocalIndisponivelError());
    vi.mocked(clientes.listar).mockResolvedValue([umCliente({ nome: "Do servidor" })]);

    const visao = await listar(EMPRESA, undefined, true);

    expect(visao.doCache).toBe(false);
    expect(visao.clientes.map((c) => c.nome)).toContain("Do servidor");
    expect(visao.pendentes.size).toBe(0);
  });

  it("salvar com rede continua salvando", async () => {
    vi.spyOn(local, "gravar").mockRejectedValue(new local.LocalIndisponivelError());
    vi.mocked(clientes.criar).mockResolvedValue(umCliente({ id: "c-1" }));

    const salvo = await salvar(EMPRESA, CORPO);

    expect(salvo.pendente).toBe(false);
    expect(clientes.criar).toHaveBeenCalled();
  });
});
