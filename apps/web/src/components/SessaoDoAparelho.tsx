interface Props {
  /** Até quando a sessão guardada abre o Decko sem rede. */
  valeAte: Date;
}

/* O aviso de que quem está dentro entrou com a sessão guardada neste aparelho.
 *
 * Fatia 5 da `docs/adr/0022-offline-first-as-respostas.md`. Aparece **sempre** enquanto a
 * sessão for local, e não dá para fechar, porque o que ele diz muda o que se pode
 * esperar da tela: as permissões são as da última sincronização, nenhuma consulta ao
 * servidor responde, e só venda e cadastro de cliente continuam de pé.
 *
 * Fica no topo e ocupa uma linha. Esconder isto faria a pessoa achar que o sistema está
 * quebrado quando a terceira tela der erro — e o prazo, escondido, viraria surpresa no
 * dia em que ele vencesse no meio da lavoura.
 */
export function SessaoDoAparelho({ valeAte }: Props) {
  const prazo = valeAte.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 bg-warn-soft px-5 py-2
                 text-center text-sm text-ink ring-1 ring-warn/30"
    >
      <span className="font-medium">Sem conexão.</span>
      <span>
        Você entrou com a sessão guardada neste aparelho, válida até {prazo}. Dá para
        vender e cadastrar cliente; o resto volta quando a rede voltar.
      </span>
    </div>
  );
}
