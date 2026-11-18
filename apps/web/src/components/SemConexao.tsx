import { useEffect, useState } from "react";

import { VALIDADE_DIAS } from "../lib/sessaoGuardada";
import { Button } from "./Button";

interface Props {
  /** Tenta restaurar a sessão de novo. */
  onTentar: () => void;
  /** Havia sessão guardada neste aparelho e o prazo dela passou.
   *
   * Muda o que a tela diz, e isso importa: prazo vencido não se resolve tentando de novo,
   * só com rede. Dizer "sua sessão continua guardada" nesse caso seria mentira. */
  sessaoVencida?: boolean;
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
 * Desde a fatia 5 da docs/adr/0022-offline-first-as-respostas.md, esta tela aparece
 * **menos**: aparelho que já entrou com rede abre com a sessão guardada e segue
 * operando. Ela sobrou para dois casos — aparelho que nunca entrou nesta empresa, e
 * sessão guardada cujo prazo venceu. */
export function SemConexao({ onTentar, sessaoVencida = false }: Props) {
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
          {sessaoVencida
            ? `O Decko abriu, mas a sessão guardada neste aparelho passou do prazo de ` +
              `${VALIDADE_DIAS} dias sem sincronizar. Entrar de novo exige rede — é o ` +
              `prazo que limita o estrago de um aparelho perdido.`
            : "O Decko abriu, mas não conseguiu falar com o servidor. Sua sessão continua " +
              "guardada neste aparelho — assim que a rede voltar, é só tentar de novo."}
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
