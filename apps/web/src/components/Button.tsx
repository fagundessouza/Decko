import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** Largura automática, para barra de ações. O padrão ocupa a linha, que é o certo
   *  dentro de formulário e no celular. */
  inline?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

/* Verde é exclusivo de ação: nenhum elemento não-acionável usa esta cor, e é isso que
 * faz o olho achar o botão sem procurar. Ver docs/BRAND.md, seção 3. */
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-action text-white shadow-sm hover:bg-action-hover hover:shadow-md " +
    "active:translate-y-px active:shadow-xs " +
    "disabled:bg-ink-faint disabled:text-white/80 disabled:shadow-none",
  secondary:
    "bg-surface text-ink ring-1 ring-line shadow-xs hover:bg-sunken hover:ring-ink-faint/40 " +
    "active:translate-y-px disabled:text-ink-faint",
  ghost:
    "bg-transparent text-ink-muted hover:bg-brand-soft hover:text-ink active:translate-y-px " +
    "disabled:text-ink-faint",
  danger:
    "bg-danger text-white shadow-sm hover:brightness-110 hover:shadow-md " +
    "active:translate-y-px disabled:bg-ink-faint",
};

const SIZES: Record<Size, string> = {
  md: "min-h-touch px-5 text-base",
  lg: "min-h-[3.25rem] px-6 text-lg",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  inline = false,
  icon,
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
        "inline-flex items-center justify-center gap-2 rounded-dk font-semibold " +
        "transition-[background-color,box-shadow,transform,color] duration-150 ease-dk " +
        "disabled:cursor-not-allowed " +
        (inline ? "w-auto " : "w-full ") +
        `${SIZES[size]} ${VARIANTS[variant]} ${className}`
      }
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="size-4 animate-spin rounded-full border-2 border-current/30 border-t-current"
        />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
