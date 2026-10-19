import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  children: ReactNode;
}

/* Verde é exclusivo de ação. Nenhum elemento não-acionável usa esta cor, para o olho
 * encontrar o botão sem procurar. Ver docs/BRAND.md, seção 3. */
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-action text-white hover:bg-action-hover active:bg-action-hover " +
    "disabled:bg-ink-muted disabled:cursor-not-allowed",
  ghost: "bg-transparent text-ink-muted hover:bg-brand-soft hover:text-ink",
};

export function Button({
  variant = "primary",
  loading = false,
  disabled,
  children,
  className = "",
  ...rest
}: Props) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading}
      className={
        "inline-flex min-h-touch w-full items-center justify-center gap-2 rounded-dk " +
        "px-5 text-lg font-semibold transition-colors " +
        `${VARIANTS[variant]} ${className}`
      }
    >
      {loading && (
        <span
          aria-hidden="true"
          className="size-5 animate-spin rounded-full border-2 border-white/40 border-t-white"
        />
      )}
      {children}
    </button>
  );
}
