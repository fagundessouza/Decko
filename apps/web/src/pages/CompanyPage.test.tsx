import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import type { TenantProfile } from "../lib/api";
import { CompanyPage } from "./CompanyPage";

/* Os dados da empresa.
 *
 * Registro no MAPA, CREA e CDA são de quem aplica defensivo. Apareciam para toda empresa,
 * no meio das inscrições, e ali pareciam exigência de qualquer negócio — numa padaria, três
 * campos de agronegócio no caminho de quem só quer pôr o CNPJ.
 *
 * Quem decide é a **ativação do módulo**, e não a permissão: o administrador recebe as
 * permissões de todos os módulos instalados na plataforma, então pelo prefixo a padaria
 * também veria. Ver docs/adr/0004-ativacao-de-modulo-por-empresa.md. */

vi.mock("../lib/api", () => ({
  tenant: { read: vi.fn(), save: vi.fn() },
}));

const { tenant } = await import("../lib/api");

const AGRO = ["Nº de registro no MAPA", "CREA", "CDA"];
const TODA_EMPRESA = [
  "Razão social",
  "CNPJ",
  "Inscrição estadual",
  "Inscrição municipal",
  "Rodapé do documento",
];

function umPerfil(sobre: Partial<TenantProfile> = {}): TenantProfile {
  return {
    id: "t-1",
    slug: "padaria",
    name: "Padaria do Teste",
    cnpj: "11222333000181",
    registro_mapa: null,
    crea: null,
    cda: null,
    inscricao_estadual: "ISENTO",
    inscricao_municipal: null,
    rodape: null,
    ...sobre,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(tenant.read).mockResolvedValue(umPerfil());
});

it("empresa sem pulverização não vê campo de agronegócio nenhum", async () => {
  render(<CompanyPage onBack={vi.fn()} temAgro={false} />);

  for (const campo of TODA_EMPRESA) {
    expect(await screen.findByLabelText(new RegExp(campo))).toBeTruthy();
  }
  for (const campo of AGRO) {
    expect(screen.queryByLabelText(new RegExp(campo))).toBeNull();
  }
  expect(screen.queryByText("Pulverização agrícola")).toBeNull();
  // E o texto da tela não promete a toda empresa um documento que ela não emite.
  expect(screen.queryByText(/Planejamento Operacional/)).toBeNull();
});

it("empresa de pulverização vê os campos, num bloco com nome", async () => {
  render(<CompanyPage onBack={vi.fn()} temAgro />);

  for (const campo of [...TODA_EMPRESA, ...AGRO]) {
    expect(await screen.findByLabelText(new RegExp(campo))).toBeTruthy();
  }
  expect(screen.getByText("Pulverização agrícola")).toBeTruthy();
  expect(screen.getByText(/Planejamento Operacional/)).toBeTruthy();
});

it("salvar sem os campos à vista não apaga o que já estava guardado", async () => {
  /* O caso real: uma empresa que teve o módulo de agro, preencheu o cabeçalho e depois o
   * desativou. A tela deixa de mostrar os três campos — e precisa devolvê-los como estão,
   * porque o `PUT` substitui o perfil inteiro. */
  const comAgro = umPerfil({ registro_mapa: "MT-00123", crea: "MT-456789", cda: "CDA-77" });
  vi.mocked(tenant.read).mockResolvedValue(comAgro);
  vi.mocked(tenant.save).mockResolvedValue(comAgro);

  render(<CompanyPage onBack={vi.fn()} temAgro={false} />);

  const razao = await screen.findByLabelText(/Razão social/);
  await userEvent.clear(razao);
  await userEvent.type(razao, "Padaria Nova");
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(tenant.save).toHaveBeenCalled());
  const enviado = vi.mocked(tenant.save).mock.calls[0][0];
  expect(enviado.name).toBe("Padaria Nova");
  expect(enviado.registro_mapa).toBe("MT-00123");
  expect(enviado.crea).toBe("MT-456789");
  expect(enviado.cda).toBe("CDA-77");
});

it("apagar a razão social não derruba a tela; só tranca o salvar", async () => {
  /* Era o caminho mais comum que existe — apagar o campo para redigitá-lo — e a tela
   * sumia: em branco virava nulo, e o botão chamava `name.trim()` em cima do nulo. */
  render(<CompanyPage onBack={vi.fn()} temAgro={false} />);

  await userEvent.clear(await screen.findByLabelText(/Razão social/));

  expect(screen.getByLabelText(/Razão social/)).toHaveProperty("value", "");
  expect(screen.getByRole("button", { name: "Salvar" })).toHaveProperty("disabled", true);
});
