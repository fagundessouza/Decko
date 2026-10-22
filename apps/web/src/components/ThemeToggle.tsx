import { useEffect, useState } from "react";

import { theme } from "../lib/session";
import type { Theme } from "../lib/session";

interface Props {
  /** Variante para a navegação escura, onde o contraste é invertido. */
  onDark?: boolean;
}

/* A escolha é da estação de trabalho e fica guardada nela. Um caixa em corredor claro e
 * outro em depósito escuro precisam de ajustes opostos, e quem sabe qual é o caso é quem
 * está na frente da tela. Ver docs/BRAND.md, seção 3. */
export function ThemeToggle({ onDark = false }: Props) {
  const [current, setCurrent] = useState<Theme>(() => theme.get());

  useEffect(() => {
    theme.apply(current);
  }, [current]);

  const next: Theme = current === "light" ? "dark" : "light";

  return (
    <button
      type="button"
      onClick={() => setCurrent(next)}
      className={
        "inline-flex min-h-touch items-center gap-2.5 rounded-dk px-3 text-base font-medium " +
        "transition-colors duration-150 ease-dk " +
        (onDark
          ? "text-white/70 hover:bg-white/5 hover:text-white"
          : "text-ink-muted hover:bg-brand-soft hover:text-ink")
      }
    >
      <span aria-hidden="true" className="text-lg">
        {current === "light" ? "◐" : "◑"}
      </span>
      {current === "light" ? "Modo escuro" : "Modo claro"}
    </button>
  );
}
