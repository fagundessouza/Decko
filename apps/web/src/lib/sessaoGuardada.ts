import type { SessionInfo } from "./api";
import { apagar, esvaziar, gravar, ler as lerDoAparelho, LocalIndisponivelError } from "./local";
import { session } from "./session";

/* A sessão guardada no aparelho, para entrar sem rede.
 *
 * Fatia 5 da `docs/adr/0022-offline-first-as-respostas.md`, decidida pelo dono do projeto
 * em 17/11/2026 — e **diferente** do que aquela ADR propunha. A proposta era PIN com hash
 * Argon2id no aparelho; a decisão foi sessão persistida com validade local:
 *
 *   "Sessão persistida com token local/TTL vence a necessidade de complicar com hash de
 *    PIN no disco."
 *
 * O caso que isto resolve é o do operador que entra na sede com 4G, vai para a lavoura e
 * **recarrega a página** ou reabre o aplicativo. Até aqui ele batia na tela "Sem conexão":
 * o arranque pedia a sessão ao servidor, e sem servidor o Decko não abria — nem para
 * vender, nem para cadastrar, nem para lançar pulverização. A fila de sincronização
 * existia e não servia para nada, porque não havia como chegar até ela.
 *
 * O que entra sem rede é a **sessão que já estava aberta**, e não uma autenticação nova.
 * A credencial é o mesmo token de renovação que já abre a sessão sozinho quando há rede —
 * recarregar a página online nunca pediu senha de novo. A diferença é que, sem rede, não
 * dá para conferir se ele foi revogado; é a resposta 4 da ADR 0022 valendo aqui: aceita o
 * que já estava valendo, e o servidor manda de volta na primeira sincronização.
 *
 * **O que isto custa, dito claramente:** nome, e-mail, papéis e permissões de quem entrou
 * ficam no disco do aparelho por até 30 dias, fora do PostgreSQL e portanto fora do Row
 * Level Security. Tablet perdido na lavoura é incidente de LGPD a tratar, não
 * contratempo, e quem o achar alcança a operação sem digitar senha. Encurtar a validade é
 * mexer num número só, logo abaixo.
 */

/** Quantos dias a sessão guardada continua abrindo o Decko sem rede.
 *
 * Trinta dias é decisão do dono do projeto, de 17/11/2026, e é o prazo da operação: a
 * pulverização de uma safra passa semanas longe de sinal. A ADR 0022 propunha sete.
 */
export const VALIDADE_DIAS = 30;

const CHAVE = "sessao";

interface Guardada {
  id: string;
  info: SessionInfo;
  /** Quando o servidor confirmou esta sessão pela última vez. */
  gravadaEm: string;
}

export interface SessaoDoAparelho {
  info: SessionInfo;
  /** Até quando ela abre o Decko sem rede. Vai para a tela: prazo escondido é surpresa. */
  vale_ate: Date;
}

export interface Leitura {
  /** A sessão que abre o Decko agora, ou nada. */
  sessao: SessaoDoAparelho | null;
  /** Havia uma, e ela venceu. Separado de "não havia nenhuma" porque a tela precisa
   *  dizer **qual** dos dois é: quem está na lavoura com o prazo vencido não tem o que
   *  tentar de novo, e quem nunca entrou neste aparelho tem. */
  vencida: boolean;
}

async function semQuebrar<T>(trabalho: Promise<T>, vazio: T): Promise<T> {
  try {
    return await trabalho;
  } catch (causa) {
    if (causa instanceof LocalIndisponivelError) return vazio;
    throw causa;
  }
}

function validadeDe(gravadaEm: string): Date {
  return new Date(new Date(gravadaEm).getTime() + VALIDADE_DIAS * 24 * 60 * 60 * 1000);
}

/** Guarda a sessão que o servidor acabou de confirmar.
 *
 * Chamada em toda leitura de sessão bem-sucedida, e não só na entrada: as permissões e os
 * módulos da empresa mudam, e o aparelho tem de guardar os últimos, não os primeiros.
 */
export async function guardar(info: SessionInfo): Promise<void> {
  const empresa = info.tenant.slug;
  if (!empresa) return;
  await semQuebrar(
    gravar<Guardada>(empresa, "sessao", {
      id: CHAVE,
      info,
      gravadaEm: new Date().toISOString(),
    }),
    undefined,
  );
}

/** A sessão que este aparelho tem para abrir sem rede, se ela ainda vale.
 *
 * Devolve nada em três casos, e os três são diferentes:
 *
 * - **Não há token de renovação.** A pessoa saiu, ou nunca entrou neste aparelho. Sem a
 *   credencial não há sessão, e a cópia guardada sozinha não vale nada.
 * - **Não há cópia guardada.** O aparelho nunca completou uma entrada com rede.
 * - **A cópia venceu.** Passou da validade, e aí exige rede — é este prazo que limita o
 *   estrago de um aparelho perdido ou de alguém que foi desligado.
 */
export async function ler(): Promise<Leitura> {
  const nada: Leitura = { sessao: null, vencida: false };
  if (!session.getRefreshToken()) return nada;

  const empresa = session.getTenantSlug();
  if (!empresa) return nada;

  const guardada = await semQuebrar(lerDoAparelho<Guardada>(empresa, "sessao", CHAVE), null);
  if (guardada === null) return nada;

  const vale_ate = validadeDe(guardada.gravadaEm);
  if (vale_ate.getTime() <= Date.now()) {
    // Vencida é apagada na hora: dado pessoal que já não serve para nada não fica.
    await semQuebrar(apagar(empresa, "sessao", CHAVE), undefined);
    return { sessao: null, vencida: true };
  }

  return { sessao: { info: guardada.info, vale_ate }, vencida: false };
}

/* O que sai do aparelho quando a pessoa sai.
 *
 * A fila **não** sai, e isso é deliberado: ela não é cache, é trabalho que aconteceu e
 * ainda não chegou ao servidor. Apagá-la na saída destruiria uma venda que o cliente
 * levou, ou um cadastro que alguém digitou — exatamente o que esta camada toda existe
 * para não deixar acontecer. O resto é cópia do que o servidor já tem, e vai embora. */
const CACHES = ["sessao", "clientes", "produtos", "avisos", "configuracao"] as const;

/** Apaga do aparelho o que era da pessoa que acabou de sair. */
export async function esquecer(): Promise<void> {
  const empresa = session.getTenantSlug();
  if (!empresa) return;
  for (const armazem of CACHES) {
    await semQuebrar(esvaziar(empresa, armazem), undefined);
  }
}
