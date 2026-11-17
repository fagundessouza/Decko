import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { restoreSession, SemRedeError } from "./api";
import { session } from "./session";

/* Sem rede não é sessão inválida.
 *
 * Este é o caso que o service worker trouxe para a frente: antes dele, abrir sem internet
 * mostrava a tela de erro do navegador e acabava ali. Agora o Decko abre — e, se a falta
 * de rede for confundida com sessão expirada, ele abre apagando a sessão de quem está no
 * meio da lavoura. A pessoa ficaria com um formulário de senha que não tem como
 * responder, justamente onde não há sinal.
 */

const TOKEN = "refresh-token-de-teste";

beforeEach(() => {
  session.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  session.clear();
});

function comRede(resposta: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resposta as Response));
}

function semRede(): void {
  // É assim que o `fetch` recusa quando não há rede: rejeita, não devolve status.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
}

it("sem rede, avisa que é falta de conexão — e guarda a sessão", async () => {
  session.setRefreshToken(TOKEN);
  semRede();

  await expect(restoreSession()).rejects.toBeInstanceOf(SemRedeError);
  // O que mais importa: o token continua aqui, esperando a rede voltar.
  expect(session.getRefreshToken()).toBe(TOKEN);
});

it("sessão recusada pelo servidor é outra coisa: a sessão sai", async () => {
  session.setRefreshToken(TOKEN);
  comRede({ ok: false, status: 401 });

  await expect(restoreSession()).resolves.toBeNull();
  expect(session.getRefreshToken()).toBeNull();
});

it("sem token guardado, não chama o servidor nem reclama de rede", async () => {
  const chamada = vi.fn();
  vi.stubGlobal("fetch", chamada);

  await expect(restoreSession()).resolves.toBeNull();
  expect(chamada).not.toHaveBeenCalled();
});
