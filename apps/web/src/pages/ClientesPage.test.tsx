import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import type { Cliente } from "../lib/clientes";
import { ClientesPage } from "./ClientesPage";

/* A carteira de clientes.
 *
 * O que este teste guarda é um apagão silencioso, e não uma regra de tela: o `PUT` de
 * cliente **substitui** o cadastro inteiro, e o vínculo com a empresa da plataforma
 * (`tenant_assinante_id`) não tem campo neste formulário. Sem ser reenviado de propósito,
 * trocar o telefone de um cliente desligaria a empresa dele da assinatura que a paga — e
 * o sintoma apareceria semanas depois, na cobrança. Ver
 * docs/adr/0021-nivel-de-plataforma.md, decisão 4. */

vi.mock("../lib/clientes", async (original) => ({
  ...(await original<typeof import("../lib/clientes")>()),
  clientes: {
    listar: vi.fn(),
    criar: vi.fn(),
    atualizar: vi.fn(),
    desativar: vi.fn(),
    reativar: vi.fn(),
  },
}));

const { clientes } = await import("../lib/clientes");

const AGRODRONE: Cliente = {
  id: "c-agrodrone",
  tipo: "juridica",
  nome: "Agrodrone LTDA",
  apelido: "Agrodrone",
  tenant_assinante_id: "t-agrodrone",
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
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(clientes.listar).mockResolvedValue([AGRODRONE]);
  vi.mocked(clientes.atualizar).mockResolvedValue(AGRODRONE);
});

it("editar um cliente não desliga a empresa da plataforma que ele é", async () => {
  render(<ClientesPage onBack={vi.fn()} />);

  await userEvent.click(await screen.findByText("Agrodrone LTDA · Agrodrone"));

  const telefone = await screen.findByLabelText(/Telefone/);
  await userEvent.clear(telefone);
  await userEvent.type(telefone, "66988887777");
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(clientes.atualizar).toHaveBeenCalled());
  const [id, corpo] = vi.mocked(clientes.atualizar).mock.calls[0];
  expect(id).toBe("c-agrodrone");
  expect(corpo.telefone).toBe("66988887777");
  // O que a tela não mostra, a tela não apaga.
  expect(corpo.tenant_assinante_id).toBe("t-agrodrone");
});

it("cliente novo nasce sem empresa da plataforma nenhuma", async () => {
  vi.mocked(clientes.criar).mockResolvedValue(AGRODRONE);
  render(<ClientesPage onBack={vi.fn()} />);

  await userEvent.click(await screen.findByRole("button", { name: /Novo cliente/ }));
  await userEvent.type(await screen.findByLabelText(/Nome/), "Maria do balcão");
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(clientes.criar).toHaveBeenCalled());
  expect(vi.mocked(clientes.criar).mock.calls[0][0].tenant_assinante_id).toBeNull();
});
