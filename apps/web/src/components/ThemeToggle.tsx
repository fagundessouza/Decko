import { useEffect, useState } from "react";

import { theme } from "../lib/session";
import type { Theme } from "../lib/session";

/* A escolha é da estação de trabalho e fica guardada nela. Um caixa em corredor claro e
 * outro em depósito escuro precisam de ajustes opostos, e quem sabe qual é o caso é quem
 * está na frente da tela. Ver docs/BRAND.md, seção 3. */
export function ThemeToggle() {
  const [current, setCurrent] = useState<Theme>(() => theme.get());

  useEffect(() => {
    theme.apply(current);
  }, [current]);

  const next: Theme = current === "light" ? "dark" : "light";

  return (
    <button
      type="button"
      onClick={() => setCurrent(next)}
      className="inline-flex min-h-touch items-center gap-2 rounded-dk px-4 text-base
                 font-medium text-ink-muted hover:bg-brand-soft hover:text-ink"
    >
      <span aria-hidden="true">{current === "light" ? "◐" : "◑"}</span>
      {current === "light" ? "Modo escuro" : "Modo claro"}
    </button>
  );
}
