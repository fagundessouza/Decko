import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Membro, Papel } from "../lib/api";
import { EquipePage } from "./EquipePage";

/* A equipe da loja.
 *
 * O que estes testes guardam é a `docs/adr/0020-operador-supervisor-e-papeis.md`:
 *
 * - quem o dono cria entra com senha inicial e **é obrigado a trocá-la**, e a tela diz
 *   quem ainda não trocou — sem isso o dono conhece a senha do operador, e "quem fez"
 *   deixa de significar alguma coisa;
 * - ninguém mexe nos próprios papéis nem desliga o próprio acesso, porque quem fizesse
 *   isso ficaria trancado do lado de fora da própria empresa. */

vi.mock("../lib/api", () => ({
  equipe: {
    listar: vi.fn(),
    papeis: vi.fn(),
    criar: vi.fn(),
    renomear: vi.fn(),
    definirPapeis: vi.fn(),
    definirSituacao: vi.fn(),
    trocarSenha: vi.fn(),
    definirPin: vi.fn(),
    removerPin: vi.fn(),
    definirCracha: vi.fn(),
  },
}));

const { equipe } = await import("../lib/api");

const EU = "u-dono";

const PAPEIS: Papel[] = [
  {
    id: "papel-op",
    name: "Operador de caixa",
    description: "Vende no balcão e abre o próprio caixa.",
    permissoes: ["pdv.venda.write", "pdv.caixa.abrir"],
  },
  {
    id: "papel-sup",
    name: "Supervisor de caixa",
    description: "Tudo do operador, mais o que exige autorização.",
    permissoes: ["pdv.venda.write", "pdv.venda.cancelar", "pdv.caixa.fechar"],
  },
];

function umMembro(sobre: Partial<Membro> = {}): Membro {
  return {
    id: "u-1",
    email: "maria@loja.com.br",
    full_name: "Maria Operadora",
    is_active: true,
    last_login_at: null,
    must_change_password: false,
    tem_pin: false,
    cracha: null,
    papeis: [{ id: "papel-op", name: "Operador de caixa", description: null }],
    ...sobre,
  };
}

function oDono(sobre: Partial<Membro> = {}): Membro {
  return umMembro({
    id: EU,
    email: "dono@loja.com.br",
    full_name: "Dono da Loja",
    papeis: [{ id: "papel-adm", name: "Administrador", description: null }],
    ...sobre,
  });
}

beforeEach(() => {
  vi.mocked(equipe.papeis).mockResolvedValue(PAPEIS);
  vi.mocked(equipe.listar).mockResolvedValue([oDono(), umMembro()]);
});

function abrir() {
  const usuario = userEvent.setup();
  render(<EquipePage onBack={() => {}} meuId={EU} />);
  return usuario;
}

describe("EquipePage", () => {
  it("lista quem trabalha na loja e o papel de cada um", async () => {
    abrir();

    expect(await screen.findByText("Maria Operadora")).toBeTruthy();
    expect(screen.getByText("Dono da Loja")).toBeTruthy();
    // Duas vezes: no nome de quem tem o papel, e no cartão que explica o papel.
    expect(screen.getAllByText("Operador de caixa")).toHaveLength(2);
  });

  it("mostra quem ainda está com a senha que o dono escolheu", async () => {
    vi.mocked(equipe.listar).mockResolvedValue([
      oDono(),
      umMembro({ must_change_password: true }),
    ]);
    abrir();

    // Enquanto a senha for a inicial, o dono a conhece — e isso precisa estar visível.
    expect(await screen.findByText("Senha ainda é a inicial")).toBeTruthy();
  });

  it("cria a pessoa com o papel escolhido e a senha inicial", async () => {
    const usuario = abrir();
    vi.mocked(equipe.criar).mockResolvedValue(umMembro({ must_change_password: true }));

    await usuario.click(await screen.findByRole("button", { name: "Nova pessoa" }));
    await usuario.type(await screen.findByLabelText("Nome"), "João Caixa");
    await usuario.type(screen.getByLabelText("E-mail"), "joao@loja.com.br");
    await usuario.type(screen.getByLabelText("Senha inicial"), "senha-de-teste-123");
    await usuario.selectOptions(screen.getByLabelText("Papel"), "papel-sup");
    await usuario.click(screen.getByRole("button", { name: "Criar acesso" }));

    await waitFor(() =>
      expect(equipe.criar).toHaveBeenCalledWith({
        email: "joao@loja.com.br",
        full_name: "João Caixa",
        senha_inicial: "senha-de-teste-123",
        papeis: ["papel-sup"],
      }),
    );
  });

  it("não deixa criar com senha curta demais", async () => {
    const usuario = abrir();

    await usuario.click(await screen.findByRole("button", { name: "Nova pessoa" }));
    await usuario.type(await screen.findByLabelText("Nome"), "João");
    await usuario.type(screen.getByLabelText("E-mail"), "joao@loja.com.br");
    await usuario.type(screen.getByLabelText("Senha inicial"), "curta");

    expect(screen.getByRole("button", { name: "Criar acesso" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("não oferece mexer em si mesmo", async () => {
    abrir();
    expect(await screen.findByText("Dono da Loja")).toBeTruthy();

    // Uma pessoa na lista é quem está olhando: trocar o próprio papel ou desligar o
    // próprio acesso trancaria quem fez isso do lado de fora da empresa.
    expect(screen.getAllByRole("button", { name: "Trocar papel" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Desligar acesso" })).toHaveLength(1);
  });

  it("trocar o papel substitui o conjunto", async () => {
    const usuario = abrir();
    vi.mocked(equipe.definirPapeis).mockResolvedValue(umMembro());

    await usuario.click(await screen.findByRole("button", { name: "Trocar papel" }));
    await usuario.selectOptions(await screen.findByLabelText("Papel"), "papel-sup");
    await usuario.click(screen.getByRole("button", { name: "Salvar papel" }));

    await waitFor(() =>
      expect(equipe.definirPapeis).toHaveBeenCalledWith("u-1", ["papel-sup"]),
    );
  });

  it("liga e desliga o acesso de quem não é você", async () => {
    const usuario = abrir();
    vi.mocked(equipe.definirSituacao).mockResolvedValue(umMembro({ is_active: false }));

    await usuario.click(await screen.findByRole("button", { name: "Desligar acesso" }));

    await waitFor(() => expect(equipe.definirSituacao).toHaveBeenCalledWith("u-1", false));
  });

  it("mostra quem já assume a estação pelo PIN, e o crachá de cada um", async () => {
    vi.mocked(equipe.listar).mockResolvedValue([
      oDono(),
      umMembro({ tem_pin: true, cracha: "CRACHA-0042" }),
    ]);
    abrir();

    expect(await screen.findByText("Tem PIN")).toBeTruthy();
    expect(screen.getByText(/crachá CRACHA-0042/)).toBeTruthy();
  });

  it("tira o PIN de quem esqueceu", async () => {
    vi.mocked(equipe.listar).mockResolvedValue([oDono(), umMembro({ tem_pin: true })]);
    vi.mocked(equipe.removerPin).mockResolvedValue(umMembro());
    const usuario = abrir();

    await usuario.click(await screen.findByRole("button", { name: "Tirar PIN" }));

    // Apagar o dono pode; escolher, não — senão o PIN deixaria de ser da pessoa.
    await waitFor(() => expect(equipe.removerPin).toHaveBeenCalledWith("u-1"));
  });

  it("não oferece tirar PIN de quem não tem", async () => {
    abrir();
    expect(await screen.findByText("Maria Operadora")).toBeTruthy();

    expect(screen.queryByRole("button", { name: "Tirar PIN" })).toBeNull();
  });

  it("emite o crachá", async () => {
    vi.mocked(equipe.definirCracha).mockResolvedValue(umMembro({ cracha: "CRACHA-7" }));
    const usuario = abrir();

    await usuario.click(await screen.findByRole("button", { name: "Crachá" }));
    await usuario.type(await screen.findByLabelText("Código do crachá"), "CRACHA-7");
    await usuario.click(screen.getByRole("button", { name: "Salvar crachá" }));

    await waitFor(() => expect(equipe.definirCracha).toHaveBeenCalledWith("u-1", "CRACHA-7"));
  });

  it("diz o que cada papel concede, para o dono ver antes de dar", async () => {
    abrir();

    expect(await screen.findByText("Vende no balcão e abre o próprio caixa.")).toBeTruthy();
    expect(screen.getByText("2 permissões")).toBeTruthy();
    expect(screen.getByText("3 permissões")).toBeTruthy();
  });
});
