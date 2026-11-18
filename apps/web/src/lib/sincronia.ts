import * as balcao from "./balcao";
import { enviarCliente } from "./carteira";
import * as lavoura from "./lavoura";
import { sincronizar, type Resultado } from "./fila";

/* Quem esvazia a fila do aparelho.
 *
 * A fila é uma só — cadastro de cliente e venda de balcão esperam no mesmo lugar, na
 * ordem em que aconteceram. Isso é de propósito: uma venda identificada depende do
 * cliente que acabou de ser cadastrado, e inverter a ordem faria o servidor recusar a
 * venda por apontar para alguém que ainda não existe lá.
 *
 * Este módulo existe só para dizer quem envia o quê. A rota é por ação, e não por tela,
 * porque quem chama é o App — uma vez ao entrar e a cada volta da rede — e ele não sabe
 * (nem precisa saber) em que tela a pessoa estava quando a conexão caiu.
 */
export function enviarPendentes(empresa: string): Promise<Resultado> {
  return sincronizar(empresa, async (item) => {
    if (item.acao === balcao.ACAO_VENDA) {
      await balcao.enviar(empresa, item);
      return;
    }
    if (item.acao === lavoura.ACAO_PLANO) {
      await lavoura.enviar(empresa, item);
      return;
    }
    await enviarCliente(empresa, item);
  });
}
