import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import type { RegistroDeVooLido } from "../lib/agro";
import { ImportarVoosPage } from "./ImportarVoosPage";

/* A tela que importa o registro de voo do equipamento.
 *
 * O que se afirma aqui é o que separa esta tela de um formulário: o arquivo é lido e
 * **nada é gravado** até alguém confirmar; o horário tem dono — o arquivo não declara
 * fuso, e quem escolhe é quem confirma; e o voo que não pulverizou aparece, porque é ele
 * que explica a diferença entre o arquivo e o documento que vai ao MAPA.
 *
 * O servidor é substituído porque este é teste de interação. Quem prova a conta da área,
 * a baixa de estoque e o horímetro é a suíte do backend, contra PostgreSQL de verdade.
 */

vi.mock("../lib/agro", async (original) => ({
  ...(await original<typeof import("../lib/agro")>()),
  agro: {
    lerRegistroDeVoo: vi.fn(),
    confirmarRegistroDeVoo: vi.fn(),
    createAircraft: vi.fn(),
  },
}));

const { agro } = await import("../lib/agro");

function umaLeitura(sobre: Partial<RegistroDeVooLido> = {}): RegistroDeVooLido {
  return {
    unidade_de_area: "mu",
    fuso_minutos: -180,
    aplicacoes: [
      {
        plot_id: "plot-a",
        talhao: "Milho 1",
        dia: "2026-08-15",
        comecou_em: "2026-08-15T18:51:36",
        terminou_em: "2026-08-15T19:10:57",
        comecou_em_ajustado: "2026-08-15T15:51:36",
        terminou_em_ajustado: "2026-08-15T16:10:57",
        area_ha: "32.2000",
        volume_l: "290.34",
        volume_por_ha: "9.02",
        duracao_segundos: 868,
        voos: 2,
        aeronave: "Valkyria",
        equipamento_serie: "SERIE-1",
        aircraft_id: "aeronave-1",
        prefixo: "PP-ABC",
        piloto: "Piloto de Teste",
        lugar: "Piracanjuba, GO",
        largura_faixa_m: "14.12",
        altura_voo_m: "6.00",
        largura_faixa_min: "14.12",
        largura_faixa_max: "14.12",
        altura_voo_min: "6.00",
        altura_voo_max: "6.00",
      },
    ],
    voos_auxiliares: [
      {
        comecou_em: "2026-08-15T19:25:14",
        terminou_em: "2026-08-15T19:33:35",
        comecou_em_ajustado: "2026-08-15T16:25:14",
        terminou_em_ajustado: "2026-08-15T16:33:35",
        duracao_segundos: 501,
        aeronave: "Valkyria",
        equipamento_serie: "SERIE-1",
        piloto: "Piloto de Teste",
        lugar: "Piracanjuba, GO",
      },
    ],
    horimetro: [
      {
        equipamento_serie: "SERIE-1",
        aeronave: "Valkyria",
        aircraft_id: "aeronave-1",
        prefixo: "PP-ABC",
        voos: 3,
        duracao_total_segundos: 1369,
        duracao_aplicando_segundos: 868,
        duracao_auxiliar_segundos: 501,
      },
    ],
    series_sem_aeronave: [],
    avisos: ["A área desta planilha está em mu, e foi convertida para hectare."],
    ...sobre,
  };
}

/** O arquivo que a pessoa escolhe. O conteúdo não importa: quem lê é o servidor. */
function umArquivo() {
  return new File([new Uint8Array([1, 2, 3])], "voos.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function abrir() {
  return render(<ImportarVoosPage onBack={() => {}} />);
}

/** O campo de arquivo, que fica escondido atrás da zona de arrastar. */
function campoDeArquivo(): HTMLInputElement {
  const campo = document.querySelector('input[type="file"]');
  if (!campo) throw new Error("a tela não tem campo de arquivo");
  return campo as HTMLInputElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(agro.lerRegistroDeVoo).mockResolvedValue(umaLeitura());
  vi.mocked(agro.confirmarRegistroDeVoo).mockResolvedValue({
    aplicacoes: 1,
    voos_gravados: 2,
    voos_repetidos: 0,
    baixas_de_estoque: 0,
    planos_atualizados: [],
    avisos: [],
  });
});

it("o arquivo escolhido é lido e nada é gravado", async () => {
  const usuario = userEvent.setup();
  abrir();

  await usuario.upload(campoDeArquivo(), umArquivo());

  expect(await screen.findByText("Milho 1 · PP-ABC")).toBeTruthy();
  // `num` corta zero à direita: a área sai "32,2 ha".
  expect(screen.getByText("32,2 ha")).toBeTruthy();
  // Ler não grava: é a regra da entrada por nota, e aqui ela vale pelo mesmo motivo.
  expect(agro.confirmarRegistroDeVoo).not.toHaveBeenCalled();
});

it("o aviso da unidade aparece antes de qualquer confirmação", async () => {
  /* Área em mu lida como hectare poria no relatório do MAPA quinze vezes a área aplicada.
   * O aviso é o que dá a chance de alguém notar. */
  const usuario = userEvent.setup();
  abrir();

  await usuario.upload(campoDeArquivo(), umArquivo());

  expect(await screen.findByText(/está em mu/)).toBeTruthy();
});

it("o voo que não pulverizou aparece, e dito como o que é", async () => {
  const usuario = userEvent.setup();
  abrir();

  await usuario.upload(campoDeArquivo(), umArquivo());

  expect(await screen.findByText("Voos que não pulverizaram")).toBeTruthy();
  expect(screen.getByText(/vão ao horímetro/)).toBeTruthy();
});

it("o controle de fuso troca o horário mostrado, sem pedir nada ao servidor", async () => {
  const usuario = userEvent.setup();
  abrir();
  await usuario.upload(campoDeArquivo(), umArquivo());
  await screen.findByText(/15:51 → 16:10/);

  await usuario.click(screen.getByRole("button", { name: /Mostrando horário local/ }));

  expect(await screen.findByText(/18:51 → 19:10/)).toBeTruthy();
  // Os dois horários vieram na mesma resposta: trocar não é nova requisição.
  expect(agro.lerRegistroDeVoo).toHaveBeenCalledTimes(1);
});

it("confirmar manda o horário escolhido, com fuso explícito", async () => {
  /* O servidor recusa horário sem deslocamento, e está certo: fuso implícito é o erro que
   * esta tela inteira existe para não repetir. O instante do arquivo vai junto, cru, e é
   * ele que faz a reimportação ser reconhecida. */
  const usuario = userEvent.setup();
  abrir();
  await usuario.upload(campoDeArquivo(), umArquivo());
  await screen.findByText("Milho 1 · PP-ABC");

  await usuario.click(
    screen.getByRole("button", { name: "Confirmar e registrar aplicação" }),
  );

  await waitFor(() => expect(agro.confirmarRegistroDeVoo).toHaveBeenCalled());
  const corpo = vi.mocked(agro.confirmarRegistroDeVoo).mock.calls[0][0];
  const voo = corpo.aplicacoes[0].voos[0];
  expect(voo.comecou_em).toMatch(/Z$/);
  expect(voo.comecou_em_arquivo).toBe("2026-08-15T18:51:36");
  expect(corpo.aplicacoes[0].area_ha).toBe("32.2000");
  // O voo auxiliar vai na lista dele, com a aeronave que o horímetro encontrou.
  expect(corpo.voos_auxiliares[0].aircraft_id).toBe("aeronave-1");
});

it("equipamento sem aeronave cadastrada abre o cadastro rápido", async () => {
  /* O relatório mensal identifica a aeronave pelo prefixo, e o arquivo só traz série. Sem
   * este caminho, a pessoa sairia da conferência no meio para cadastrar em outra tela. */
  const usuario = userEvent.setup();
  vi.mocked(agro.lerRegistroDeVoo).mockResolvedValue(
    umaLeitura({ series_sem_aeronave: ["SERIE-NOVA"] }),
  );
  vi.mocked(agro.createAircraft).mockResolvedValue({
    id: "aeronave-2",
    prefixo: "PP-NEW",
    modelo: null,
    fabricante: null,
    numero_serie: "SERIE-NOVA",
    is_active: true,
  });
  abrir();
  await usuario.upload(campoDeArquivo(), umArquivo());

  await usuario.click(await screen.findByRole("button", { name: /Cadastrar SERIE-NOVA/ }));
  await usuario.type(screen.getByLabelText(/Prefixo/), "PP-NEW");
  await usuario.click(screen.getByRole("button", { name: "Cadastrar" }));

  await waitFor(() =>
    expect(agro.createAircraft).toHaveBeenCalledWith({
      prefixo: "PP-NEW",
      modelo: null,
      fabricante: null,
      numero_serie: "SERIE-NOVA",
    }),
  );
});

it("arquivo recusado pelo servidor mostra o motivo, e não some com a tela", async () => {
  const usuario = userEvent.setup();
  vi.mocked(agro.lerRegistroDeVoo).mockRejectedValue(
    new Error("Não reconheço a unidade de área desta planilha."),
  );
  abrir();

  await usuario.upload(campoDeArquivo(), umArquivo());

  expect(await screen.findByText(/unidade de área/)).toBeTruthy();
  expect(screen.getByText(/Arraste aqui o arquivo de voos/)).toBeTruthy();
});

it("escolhido o horário do arquivo, é ele que vai ao servidor", async () => {
  /* O controle de fuso não é só exibição: ele decide qual horário fica registrado. Se
   * mostrasse um e mandasse outro, a tela estaria mentindo no ponto mais sensível. */
  const usuario = userEvent.setup();
  abrir();
  await usuario.upload(campoDeArquivo(), umArquivo());
  await screen.findByText("Milho 1 · PP-ABC");

  await usuario.click(screen.getByRole("button", { name: /Mostrando horário local/ }));
  await usuario.click(
    screen.getByRole("button", { name: "Confirmar e registrar aplicação" }),
  );

  await waitFor(() => expect(agro.confirmarRegistroDeVoo).toHaveBeenCalled());
  const voo = vi.mocked(agro.confirmarRegistroDeVoo).mock.calls[0][0].aplicacoes[0].voos[0];
  // Comparado com a mesma conversão, para o teste não depender do fuso da máquina.
  expect(voo.comecou_em).toBe(new Date("2026-08-15T18:51:36").toISOString());
});
