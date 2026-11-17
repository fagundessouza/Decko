/* O pacote guardado no aparelho, e como ele é trocado.
 *
 * O registro mora aqui, e não num componente, por dois motivos. Primeiro, ele precisa
 * acontecer uma vez por carregamento, e não por montagem. Segundo, o módulo virtual
 * `virtual:pwa-register` só existe quando o plugin está no build — importá-lo de dentro
 * de um componente arrastaria essa dependência para todo teste que montasse a tela.
 *
 * A atualização é **oferecida**, nunca aplicada sozinha: o alvo inclui PDV, e recarregar
 * a página no meio de uma venda perde o que está na tela.
 */

export const EVENTO_ATUALIZACAO = "decko:atualizacao-disponivel";

let aplicar: ((recarregar?: boolean) => Promise<void>) | null = null;

/** Guarda a função que troca a versão, e avisa a interface que existe uma esperando. */
export function anunciarAtualizacao(trocar: (recarregar?: boolean) => Promise<void>): void {
  aplicar = trocar;
  window.dispatchEvent(new CustomEvent(EVENTO_ATUALIZACAO));
}

/** Aplica a versão nova e recarrega. Só é chamada por quem está operando. */
export async function aplicarAtualizacao(): Promise<void> {
  await aplicar?.(true);
}
