import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import type { EmpresaDaPlataforma } from "../lib/api";
import type { Cliente } from "../lib/clientes";
import { MeusClientesPage } from "./MeusClientesPage";

/* A área de quem vende o Decko.
 *
 * O que estes testes guardam é a `docs/adr/0021-nivel-de-plataforma.md`:
 *
 * - a tela mostra **só o que a tabela `tenant` já diz**, porque ler de dentro de empresa
 *   alheia é travessia do isolamento, e travessia é decisão própria (decisão 3);
 * - uma empresa é apontada por **um contato só**: duas assinaturas pagando o mesmo acesso
 *   tornaria "está bloqueada?" uma pergunta sem resposta (decisão 4);
 * - e ligar o contato à empresa reenvia o cadastro **inteiro**, porque o `PUT` substitui:
 *   mandar só o vínculo apagaria documento, endereço e contato em silêncio. */

vi.mock("../lib/api", () => ({
  authedJson: vi.fn(),
  plataforma: { empresas: vi.fn() },
}));

/* O `comoEntrada` entra de verdade: é ele que evita o apagão silencioso, e trocá-lo por
 * um dublê deixaria o teste do corpo completo sem nada para provar. */
vi.mock("../lib/clientes", async (original) => ({
  ...(await original<typeof import("../lib/clientes")>()),
  clientes: { listar: vi.fn(), atualizar: vi.fn() },
}));

const { plataforma } = await import("../lib/api");
const { clientes } = await import("../lib/clientes");

const AGRODRONE: EmpresaDaPlataforma = {
  id: "t-agrodrone",
  slug: "agrodrone",
  name: "Agrodrone Serviços e Agronegócios",
  is_active: true,
  created_at: "2026-11-13T19:05:00+00:00",
};

const DECKO: EmpresaDaPlataforma = {
  id: "t-decko",
  slug: "decko",
  name: "Decko",
  is_active: true,
  created_at: "2026-10-01T12:00:00+00:00",
};

function umContato(sobre: Partial<Cliente> = {}): Cliente {
  return {
    id: "c-1",
    tipo: "juridica",
    nome: "Agrodrone LTDA",
    apelido: "Agrodrone",
    tenant_assinante_id: null,
    cpf_cnpj: "11222333000181",
    inscricao_estadual: "ISENTO",
    email: "contato@agrodrone.com.br",
    telefone: "66999990000",
    cep: "78550000",
    logradouro: "Avenida Brasil",
    numero: "100",
    complemento: null,
    bairro: "Centro",
    cidade: "Sinop",
    uf: "MT",
    observacao: null,
    ativo: true,
    ...sobre,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(plataforma.empresas).mockResolvedValue([AGRODRONE, DECKO]);
  vi.mocked(clientes.listar).mockResolvedValue([umContato()]);
});

it("mostra as empresas na ordem que o servidor manda, com o apelido e a data de entrada", async () => {
  render(<MeusClientesPage onBack={vi.fn()} />);

  const nomes = await screen.findAllByText(/Agrodrone Serviços|^Decko$/);
  expect(nomes.map((no) => no.textContent)).toEqual([
    "Agrodrone Serviços e Agronegócios",
    "Decko",
  ]);
  expect(screen.getByText(/agrodrone/)).toBeTruthy();
  expect(screen.getByText(/entrou em 13\/11\/2026/)).toBeTruthy();
});

it("diz em qual contato cada empresa é cobrada", async () => {
  vi.mocked(clientes.listar).mockResolvedValue([
    umContato({ tenant_assinante_id: AGRODRONE.id }),
  ]);

  render(<MeusClientesPage onBack={vi.fn()} />);

  expect(await screen.findByText(/Cobrada no contato/)).toBeTruthy();
  expect(screen.getByText("Agrodrone LTDA")).toBeTruthy();
  // A ligada mostra como desfazer; a que não tem contato mostra como ligar.
  expect(screen.getAllByRole("button", { name: "Ligar a um contato" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "Desligar" })).toHaveLength(1);
});

it("ao ligar, reenvia o cadastro inteiro do contato, e não só o vínculo", async () => {
  vi.mocked(clientes.atualizar).mockResolvedValue(umContato());
  render(<MeusClientesPage onBack={vi.fn()} />);

  const botoes = await screen.findAllByRole("button", { name: "Ligar a um contato" });
  await userEvent.click(botoes[0]);
  await userEvent.selectOptions(
    await screen.findByLabelText("Contato da carteira"),
    "c-1",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ligar" }));

  await waitFor(() => expect(clientes.atualizar).toHaveBeenCalled());
  const [id, corpo] = vi.mocked(clientes.atualizar).mock.calls[0];
  expect(id).toBe("c-1");
  expect(corpo.tenant_assinante_id).toBe(AGRODRONE.id);
  // O `PUT` substitui o cadastro: o que não for mandado volta a nulo no banco.
  expect(corpo.cpf_cnpj).toBe("11222333000181");
  expect(corpo.cidade).toBe("Sinop");
  expect(corpo.telefone).toBe("66999990000");
  expect(corpo.inscricao_estadual).toBe("ISENTO");
});

it("não oferece contato que já é outra empresa da plataforma", async () => {
  vi.mocked(clientes.listar).mockResolvedValue([
    umContato({ id: "c-ocupado", nome: "Já é a Decko", tenant_assinante_id: DECKO.id }),
    umContato({ id: "c-livre", nome: "Contato livre" }),
  ]);

  render(<MeusClientesPage onBack={vi.fn()} />);
  await userEvent.click(
    (await screen.findAllByRole("button", { name: "Ligar a um contato" }))[0],
  );

  const escolha = await screen.findByLabelText("Contato da carteira");
  expect(escolha.textContent).toContain("Contato livre");
  expect(escolha.textContent).not.toContain("Já é a Decko");
});

it("desligar manda o vínculo nulo, sem mexer no resto do cadastro", async () => {
  const ligado = umContato({ tenant_assinante_id: AGRODRONE.id });
  vi.mocked(clientes.listar).mockResolvedValue([ligado]);
  vi.mocked(clientes.atualizar).mockResolvedValue(umContato());

  render(<MeusClientesPage onBack={vi.fn()} />);
  await userEvent.click(await screen.findByRole("button", { name: "Desligar" }));

  await waitFor(() => expect(clientes.atualizar).toHaveBeenCalled());
  const [, corpo] = vi.mocked(clientes.atualizar).mock.calls[0];
  expect(corpo.tenant_assinante_id).toBeNull();
  expect(corpo.nome).toBe("Agrodrone LTDA");
  expect(corpo.cpf_cnpj).toBe("11222333000181");
});

it("sem a carteira de clientes, as empresas continuam aparecendo", async () => {
  vi.mocked(clientes.listar).mockRejectedValue(new Error("Não encontrado."));

  render(<MeusClientesPage onBack={vi.fn()} />);

  expect(await screen.findByText("Agrodrone Serviços e Agronegócios")).toBeTruthy();
  expect(screen.getByText(/não tem a carteira de clientes instalada/)).toBeTruthy();
  // Sem carteira não há contato para escolher, e o botão diz isso estando desligado.
  for (const botao of screen.getAllByRole("button", { name: "Ligar a um contato" })) {
    expect(botao).toHaveProperty("disabled", true);
  }
});

it("quando a área recusa, diz o motivo em vez de lista vazia calada", async () => {
  vi.mocked(plataforma.empresas).mockRejectedValue(new Error("Não encontrado."));

  render(<MeusClientesPage onBack={vi.fn()} />);

  expect(await screen.findByText("Não encontrado.")).toBeTruthy();
});
