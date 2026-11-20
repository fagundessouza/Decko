import "fake-indexeddb/auto";

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

/* Abrir sem rede não pode cair na tela de entrada.
 *
 * O service worker fez o Decko abrir sem internet — e abrir no formulário de senha é pior
 * do que a tela de erro do navegador: a pessoa digita a senha certa, nada acontece, e a
 * conclusão razoável é que o sistema quebrou. Pior ainda no campo, onde não há como
 * conseguir rede para responder ao formulário. */

vi.mock("./lib/api", async (original) => ({
  ...(await original<typeof import("./lib/api")>()),
  restoreSession: vi.fn(),
  renewSession: vi.fn(),
  logout: vi.fn(),
}));

const { restoreSession, SemRedeError } = await import("./lib/api");
const { default: App } = await import("./App");

beforeEach(() => {
  vi.clearAllMocks();
});

it("sem rede, mostra 'Sem conexão' em vez do formulário de entrada", async () => {
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());

  render(<App />);

  expect(await screen.findByText("Sem conexão")).toBeTruthy();
  expect(screen.queryByLabelText(/Código da empresa/)).toBeNull();
});

it("'Tentar de novo' pergunta ao servidor outra vez", async () => {
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());
  render(<App />);
  await screen.findByText("Sem conexão");
  expect(restoreSession).toHaveBeenCalledTimes(1);

  // A rede voltou, e agora a sessão restaura.
  vi.mocked(restoreSession).mockResolvedValue(null);
  await userEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));

  expect(restoreSession).toHaveBeenCalledTimes(2);
  // Sem sessão e com rede, aí sim é a tela de entrada.
  expect(await screen.findByLabelText(/Código da empresa/)).toBeTruthy();
});

it("sessão que o servidor recusou leva para a entrada, e não para 'Sem conexão'", async () => {
  vi.mocked(restoreSession).mockResolvedValue(null);

  render(<App />);

  expect(await screen.findByLabelText(/Código da empresa/)).toBeTruthy();
  expect(screen.queryByText("Sem conexão")).toBeNull();
});

it("erro que não é de rede não vira 'Sem conexão'", async () => {
  /* Dizer "sem conexão" para um defeito manda a pessoa conferir o roteador por causa de
   * um problema que está no sistema. A mensagem errada custa a tarde de alguém. */
  vi.mocked(restoreSession).mockRejectedValue(new Error("qualquer outra coisa"));

  render(<App />);

  expect(await screen.findByLabelText(/Código da empresa/)).toBeTruthy();
  expect(screen.queryByText("Sem conexão")).toBeNull();
});

/* Recarregar sem rede tem de abrir o Decko, e não a parede.
 *
 * Fatia 5 da `docs/adr/0022-offline-first-as-respostas.md`, decidida em 17/11/2026: sessão
 * persistida com validade local. O caso é o do operador que entra na sede com 4G, vai para
 * a lavoura e recarrega a página — até aqui ele batia em "Sem conexão", e a fila de
 * sincronização existia sem servir para nada, porque não havia como chegar até ela.
 */
const { session } = await import("./lib/session");
const sessaoGuardada = await import("./lib/sessaoGuardada");
const local = await import("./lib/local");

const EMPRESA = "fazenda-do-arranque";

function umaSessao() {
  return {
    user: {
      id: "user-1",
      email: "piloto@teste-decko.com.br",
      full_name: "João Piloto",
      is_active: true,
      last_login_at: null,
      must_change_password: false,
      tem_pin: true,
    },
    tenant: { id: "tenant-1", name: "Fazenda do Arranque", slug: EMPRESA },
    // Sem `core.module.activate`: empresa já montada vai para o menu, e não para a
    // escolha do ramo.
    permissions: ["pdv.venda.write"],
    is_platform_admin: false,
    active_modules: ["pdv"],
  };
}

async function comSessaoGuardada() {
  localStorage.clear();
  local.fechar();
  await local.esvaziar(EMPRESA, "sessao");
  session.setTenantSlug(EMPRESA);
  session.setRefreshToken("token-de-renovacao-do-teste");
  await sessaoGuardada.guardar(umaSessao());
}

it("sem rede, abre com a sessão guardada no aparelho", async () => {
  await comSessaoGuardada();
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());

  render(<App />);

  // O sistema abre, e diz em que condição está — permissões da última sincronização.
  expect(
    await screen.findByText(/entrou com a sessão guardada neste aparelho/i),
  ).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Sem conexão" })).toBeNull();
  expect(screen.queryByLabelText(/Código da empresa/)).toBeNull();
});

it("sem rede e sem sessão guardada, continua sendo a parede", async () => {
  /* Aparelho que nunca entrou nesta empresa não tem como abrir: a credencial é do
   * servidor, e entrar sem rede é continuar uma sessão, não criar uma. */
  localStorage.clear();
  local.fechar();
  await local.esvaziar(EMPRESA, "sessao");
  session.setTenantSlug(EMPRESA);
  session.setRefreshToken("token-de-renovacao-do-teste");
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Sem conexão" })).toBeTruthy();
});

it("a rede que volta confere a sessão com o servidor, sem remontar a tela", async () => {
  /* Em silêncio de propósito: pode haver venda em andamento no balcão, e reiniciar o
   * arranque levaria embora o que está na tela. */
  await comSessaoGuardada();
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());
  render(<App />);
  await screen.findByText(/entrou com a sessão guardada neste aparelho/i);

  vi.mocked(restoreSession).mockResolvedValue(umaSessao() as never);
  await act(async () => {
    /* `act` descarrega os efeitos pendentes antes de disparar. Sem ele, o evento — que é
       síncrono — pode cair no intervalo entre o texto aparecer na tela e o `useEffect`
       registrar o ouvinte do "online", e aí se perde para sempre. Era essa corrida, e não
       lentidão, que derrubava este arquivo sob a suíte inteira: aumentar o tempo de espera
       não resolvia porque o evento nunca tinha chegado. */
    window.dispatchEvent(new Event("online"));
  });

  await waitFor(
    () => expect(screen.queryByText(/entrou com a sessão guardada neste aparelho/i)).toBeNull(),
    /* INTERMITENTE, e o prazo não é a causa.
     *
     * Sozinho este arquivo passa em menos de dois segundos, sempre. Dentro da suíte
     * inteira ele falha de vez em quando — e, quando falha com 15s de prazo, falha com a
     * mesma mensagem que com 5s: *o aviso continua na tela*. Ou seja, em algumas execuções
     * o tratamento do "online" não acontece, e esperar mais não ajuda.
     *
     * O que já foi descartado: o empate entre o prazo da espera e o do teste (corrigido
     * abaixo), a corrida de registrar o ouvinte depois do disparo (corrigida pelo `act`
     * acima) e a saturação da máquina (`maxWorkers` em 50% no `vite.config.ts`, que
     * reduziu muito a frequência). O que falta investigar é o que, sob concorrência, faz
     * o `restoreSession` do ouvinte não chegar a limpar a sessão local. */
    { timeout: 5000 },
  );
  /* O limite do teste precisa ser **maior** que o da espera: senão ele morre antes de
     usar a janela que pediu, e era esse empate — 5000 contra 5000 — um dos defeitos
     deste arquivo. */
}, 15000);

it("sessão que o servidor recusou quando a rede voltou leva para a entrada", async () => {
  // "Aceita o que já passou, barra o que vem depois da sincronização" — ADR 0022.
  await comSessaoGuardada();
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());
  render(<App />);
  await screen.findByText(/entrou com a sessão guardada neste aparelho/i);

  vi.mocked(restoreSession).mockResolvedValue(null);
  await act(async () => {
    /* `act` descarrega os efeitos pendentes antes de disparar. Sem ele, o evento — que é
       síncrono — pode cair no intervalo entre o texto aparecer na tela e o `useEffect`
       registrar o ouvinte do "online", e aí se perde para sempre. Era essa corrida, e não
       lentidão, que derrubava este arquivo sob a suíte inteira: aumentar o tempo de espera
       não resolvia porque o evento nunca tinha chegado. */
    window.dispatchEvent(new Event("online"));
  });

  /* Com folga de tempo: este teste monta a aplicação inteira, e com a suíte toda rodando
   * em paralelo o padrão de um segundo da biblioteca estoura por lentidão da máquina — o
   * que faz o teste falhar sem nada estar errado no produto. */
  expect(
    await screen.findByLabelText(/Código da empresa/, {}, { timeout: 5000 }),
  ).toBeTruthy();
}, 15000);
