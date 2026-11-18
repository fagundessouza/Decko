import "fake-indexeddb/auto";

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { SessionInfo } from "./api";

/* A sessão guardada no aparelho, que abre o Decko sem rede.
 *
 * Fatia 5 da `docs/adr/0022-offline-first-as-respostas.md`, na forma que o dono do
 * projeto decidiu em 17/11/2026: sessão persistida com validade local, e não PIN com hash
 * no disco.
 *
 * O que se afirma aqui é o que **limita** essa sessão, porque é aí que está o risco. Ela
 * não vale sem a credencial, não vale depois do prazo, não atravessa de uma empresa para
 * outra, e sai do aparelho quando a pessoa sai. A fila é a única coisa que fica — ela não
 * é cópia, é venda que aconteceu e ainda não subiu.
 */

const { guardar, ler, esquecer, VALIDADE_DIAS } = await import("./sessaoGuardada");
const { session } = await import("./session");
const local = await import("./local");

const EMPRESA = "fazenda-do-teste";

function umaSessao(sobre: Partial<SessionInfo> = {}): SessionInfo {
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
    tenant: { id: "tenant-1", name: "Fazenda do Teste", slug: EMPRESA },
    permissions: ["pdv.venda.write"],
    is_platform_admin: false,
    active_modules: ["pdv"],
    ...sobre,
  };
}

const DIA = 24 * 60 * 60 * 1000;

/* Só o relógio é adiantado, e não os temporizadores: o IndexedDB depende de `setTimeout`
 * para completar transação, e congelá-lo trava o teste em vez de testar o prazo. */
function adiantar(dias: number): void {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(Date.now() + dias * DIA));
}

beforeEach(async () => {
  vi.useRealTimers();
  localStorage.clear();
  local.fechar();
  for (const armazem of ["sessao", "clientes", "produtos", "fila", "configuracao"] as const) {
    await local.esvaziar(EMPRESA, armazem);
  }
  session.setTenantSlug(EMPRESA);
  session.setRefreshToken("token-de-renovacao-do-teste");
});

afterEach(() => {
  vi.useRealTimers();
  local.fechar();
});

it("dentro do prazo, a sessão guardada abre o Decko", async () => {
  await guardar(umaSessao());

  const { sessao, vencida } = await ler();

  expect(vencida).toBe(false);
  expect(sessao?.info.user.full_name).toBe("João Piloto");
  // O prazo vai para a tela: prazo escondido é surpresa no dia em que vence.
  expect(sessao?.vale_ate.getTime()).toBeGreaterThan(Date.now() + (VALIDADE_DIAS - 1) * DIA);
});

it("sem a credencial, a cópia guardada não vale nada", async () => {
  /* O token de renovação **é** a credencial, e é o mesmo que abre a sessão sozinho quando
   * há rede. Sem ele a pessoa saiu, e a cópia sozinha não pode abrir nada. */
  await guardar(umaSessao());
  session.clear();

  expect((await ler()).sessao).toBeNull();
});

it("passado o prazo, não abre — e a cópia é apagada na hora", async () => {
  /* É este prazo que limita o estrago de um aparelho perdido ou de alguém que foi
   * desligado: sem rede não há como conferir se o token foi revogado. */
  await guardar(umaSessao());

  adiantar(VALIDADE_DIAS + 1);

  const primeira = await ler();
  expect(primeira.sessao).toBeNull();
  expect(primeira.vencida).toBe(true);

  // Dado pessoal que já não serve para nada não fica no disco de ninguém.
  vi.useRealTimers();
  const depois = await ler();
  expect(depois.sessao).toBeNull();
  expect(depois.vencida).toBe(false);
});

it("a véspera do prazo ainda abre", async () => {
  // A borda é onde se erra, e errar para o lado de travar é parar a lavoura.
  await guardar(umaSessao());

  adiantar(VALIDADE_DIAS - 1);

  expect((await ler()).sessao).not.toBeNull();
});

it("o prazo conta da última vez que o servidor confirmou, e não da primeira", async () => {
  /* Quem passa na sede toda semana nunca deveria ver a sessão vencer: cada sincronização
   * renova o prazo. */
  await guardar(umaSessao());

  adiantar(VALIDADE_DIAS - 2);
  await guardar(umaSessao());

  adiantar(VALIDADE_DIAS - 2);
  expect((await ler()).sessao).not.toBeNull();
});

it("a sessão de uma empresa não abre a outra", async () => {
  /* O isolamento entre empresas no servidor é do PostgreSQL; aqui é o nome do banco do
   * aparelho. Trocar de empresa é entrar de novo — ADR 0012. */
  await guardar(umaSessao());

  session.setTenantSlug("outra-fazenda");

  expect((await ler()).sessao).toBeNull();
});

it("guarda as permissões e os módulos da última sincronização", async () => {
  // São eles que decidem o menu sem rede. Guardar os primeiros faria o menu mentir.
  await guardar(umaSessao({ permissions: ["pdv.venda.write"], active_modules: ["pdv"] }));
  await guardar(
    umaSessao({ permissions: ["pdv.venda.write", "agro.plano.write"], active_modules: ["pdv", "agro"] }),
  );

  const { sessao } = await ler();
  expect(sessao?.info.permissions).toContain("agro.plano.write");
  expect(sessao?.info.active_modules).toEqual(["pdv", "agro"]);
});

it("sair apaga a sessão e o cadastro guardados neste aparelho", async () => {
  await guardar(umaSessao());
  await local.gravar(EMPRESA, "clientes", { id: "cliente-1", nome: "Maria" });

  await esquecer();

  expect((await ler()).sessao).toBeNull();
  expect(await local.lerTodos(EMPRESA, "clientes")).toEqual([]);
});

it("sair **não** apaga a fila: ela é venda que aconteceu", async () => {
  /* A fila não é cópia do que o servidor tem — é trabalho que aconteceu e ainda não
   * chegou lá. Apagá-la na saída destruiria uma venda que o cliente levou. */
  const { enfileirar, pendentes } = await import("./fila");
  await enfileirar(EMPRESA, { id: "venda-1", acao: "venda.sincronizar", corpo: {} });

  await esquecer();

  expect(await pendentes(EMPRESA)).toHaveLength(1);
});
