import { ApiError, SemRedeError } from "./api";
import { apagar, gravar, lerTodos, type Armazem } from "./local";

/* A fila de escritas que ainda não chegaram ao servidor.
 *
 * É a decisão 3 da docs/adr/0019-offline-first.md: a escrita nasce no aparelho e a fila
 * esvazia sozinha quando a rede volta, sem a pessoa pedir e sem tela de "sincronizando".
 *
 * A fila guarda o corpo inteiro da operação, e não um diff. É o que permite reenviar sem
 * depender do que havia antes — e, com a identidade vindo do aparelho (ADR 0022, fatia 1),
 * reenviar o mesmo item duas vezes não duplica nada do outro lado.
 */

const ARMAZEM: Armazem = "fila";

export type Acao = "cliente.criar" | "cliente.atualizar";

export interface Pendente {
  /** A identidade da **entidade**, não da operação.
   *
   * Duas edições do mesmo cliente feitas offline não viram dois itens na fila: a segunda
   * substitui a primeira. Mandar as duas seria mandar um estado que ninguém mais quer, e
   * o servidor registraria uma alteração que durou três segundos no aparelho. */
  id: string;
  acao: Acao;
  corpo: unknown;
  /** Hora do aparelho. A ADR 0019 avisa que esta e a hora do servidor divergem, e que a
   *  trilha precisa das duas — por isso ela viaja junto. */
  criadoEm: string;
  tentativas: number;
  /** O que o servidor respondeu da última vez, quando ele recusou. */
  erro?: string;
}

export const EVENTO_FILA = "decko:fila-mudou";

function avisar(): void {
  window.dispatchEvent(new CustomEvent(EVENTO_FILA));
}

export async function enfileirar(
  empresa: string,
  item: { id: string; acao: Acao; corpo: unknown },
): Promise<void> {
  const pendente: Pendente = {
    ...item,
    criadoEm: new Date().toISOString(),
    tentativas: 0,
  };
  await gravar(empresa, ARMAZEM, pendente);
  avisar();
}

export async function pendentes(empresa: string): Promise<Pendente[]> {
  const todos = await lerTodos<Pendente>(empresa, ARMAZEM);
  // Da mais antiga para a mais nova: a ordem em que aconteceram é a ordem em que entram.
  return todos.sort((a, b) => a.criadoEm.localeCompare(b.criadoEm));
}

export async function esquecer(empresa: string, id: string): Promise<void> {
  await apagar(empresa, ARMAZEM, id);
  avisar();
}

export interface Resultado {
  enviados: number;
  recusados: number;
  /** Parou porque a rede caiu de novo. O que sobrou continua na fila. */
  semRede: boolean;
}

/** Envia o que está na fila, do mais antigo para o mais novo.
 *
 * Três desfechos por item, e eles são diferentes de propósito:
 *
 * - **Aceito:** sai da fila.
 * - **Recusado pelo servidor** (422, por exemplo): **fica** na fila, com o motivo
 *   guardado. Tentar de novo não resolveria, e apagar esconderia da pessoa que o cadastro
 *   dela não entrou. A divergência tem de aparecer — ADR 0022.
 * - **Sem rede:** para tudo e devolve. Continuar gastaria a fila inteira em erro de rede e
 *   encheria o contador de tentativas sem motivo.
 */
export async function sincronizar(
  empresa: string,
  enviar: (item: Pendente) => Promise<void>,
): Promise<Resultado> {
  const resultado: Resultado = { enviados: 0, recusados: 0, semRede: false };

  for (const item of await pendentes(empresa)) {
    // Item já recusado não é tentado de novo sozinho: o servidor já disse não, e repetir
    // em toda reconexão seria insistir num erro que só uma pessoa resolve.
    if (item.erro) continue;

    try {
      await enviar(item);
      await apagar(empresa, ARMAZEM, item.id);
      resultado.enviados += 1;
    } catch (causa) {
      if (causa instanceof SemRedeError) {
        resultado.semRede = true;
        break;
      }
      const motivo = causa instanceof ApiError ? causa.message : String(causa);
      await gravar(empresa, ARMAZEM, {
        ...item,
        tentativas: item.tentativas + 1,
        erro: motivo,
      });
      resultado.recusados += 1;
    }
  }

  if (resultado.enviados > 0 || resultado.recusados > 0) avisar();
  return resultado;
}
