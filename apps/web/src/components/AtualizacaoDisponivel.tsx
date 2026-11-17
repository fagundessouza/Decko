import { useEffect, useState } from "react";

import { aplicarAtualizacao, EVENTO_ATUALIZACAO } from "../lib/pwa";
import { Button } from "./Button";

/* O aviso de que existe versão nova guardada, esperando para entrar.
 *
 * Com o pacote guardado no aparelho, atualizar deixa de ser consequência de recarregar a
 * página: a versão antiga continuaria abrindo para sempre se ninguém trocasse. Por outro
 * lado, trocar sozinho recarrega a página — e no caixa isso cai no meio de uma venda.
 *
 * Então o sistema avisa e espera. Fica discreto, no rodapé, e não interrompe nada: quem
 * está vendendo termina a venda e atualiza depois. */
export function AtualizacaoDisponivel() {
  const [tem, setTem] = useState(false);
  const [aplicando, setAplicando] = useState(false);

  useEffect(() => {
    const avisar = () => setTem(true);
    window.addEventListener(EVENTO_ATUALIZACAO, avisar);
    return () => window.removeEventListener(EVENTO_ATUALIZACAO, avisar);
  }, []);

  if (!tem) return null;

  return (
    <div
      role="status"
      className="fixed inset-x-0 bottom-0 z-50 flex flex-wrap items-center justify-center gap-3 border-t border-line-subtle bg-surface px-5 py-3 shadow-lg"
    >
      <p className="text-base text-ink">Há uma versão nova do Decko neste aparelho.</p>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          inline
          onClick={() => setTem(false)}
          disabled={aplicando}
        >
          Depois
        </Button>
        <Button
          inline
          loading={aplicando}
          onClick={() => {
            setAplicando(true);
            void aplicarAtualizacao();
          }}
        >
          Atualizar agora
        </Button>
      </div>
    </div>
  );
}
