import { useEffect, useState } from "react";

import { Button } from "./Button";

interface Props {
  /** Tenta restaurar a sessão de novo. */
  onTentar: () => void;
}

/* O que aparece quando o aparelho abriu sem conseguir falar com o servidor.
 *
 * Antes do service worker, esse caso era a tela de erro do próprio navegador. Depois
 * dele, o Decko abre — e abria direto no formulário de entrada, que é pior: a pessoa
 * digita a senha certa, nada acontece, e a conclusão razoável é que o sistema quebrou ou
 * que a senha mudou.
 *
 * A sessão guardada **não** é apagada nesse caso. Quem estava dentro continua dentro
 * assim que a rede voltar; é o que `SemRedeError` existe para distinguir.
 *
 * O que esta tela não faz é deixar trabalhar sem rede. Isso é a outra metade do
 * offline-first, e depende das perguntas em aberto da docs/adr/0019-offline-first.md. */
export function SemConexao({ onTentar }: Props) {
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const voltou = () => setOnline(true);
    const caiu = () => setOnline(false);
    window.addEventListener("online", voltou);
    window.addEventListener("offline", caiu);
    return () => {
      window.removeEventListener("online", voltou);
      window.removeEventListener("offline", caiu);
    };
  }, []);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-5">
      <div className="w-full max-w-md text-center">
        <h1 className="text-2xl font-bold tracking-tight text-ink">Sem conexão</h1>
        <p className="mt-3 text-base text-ink-muted">
          O Decko abriu, mas não conseguiu falar com o servidor. Sua sessão continua
          guardada neste aparelho — assim que a rede voltar, é só tentar de novo.
        </p>

        {/* O aviso do próprio aparelho, quando ele sabe. `navigator.onLine` diz que existe
            rede, e não que o servidor responde: por isso ele acrescenta informação aqui,
            mas não substitui a tentativa. */}
        <p className="mt-4 text-sm text-ink-muted" role="status">
          {online
            ? "Este aparelho está conectado, então o problema pode ser do servidor ou do caminho até ele."
            : "Este aparelho está sem rede."}
        </p>

        <div className="mt-8">
          <Button onClick={onTentar}>Tentar de novo</Button>
        </div>
      </div>
    </div>
  );
}
