import type { ReactNode } from "react";

type Tone = "danger" | "warn" | "info" | "success";

const TONES: Record<Tone, { box: string; mark: string }> = {
  danger: { box: "bg-danger-soft text-danger ring-danger/20", mark: "!" },
  warn: { box: "bg-warn-soft text-ink ring-warn/30", mark: "⚠" },
  info: { box: "bg-brand-soft text-ink ring-brand-link/15", mark: "i" },
  success: { box: "bg-action-soft text-ink ring-action/20", mark: "✓" },
};

interface Props {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  action?: ReactNode;
}

/* Aviso com símbolo e texto, nunca só cor: daltonismo e tela de PDV desbotada são
 * realidade no público-alvo. Ver docs/BRAND.md.
 *
 * Existe como primitivo porque o mesmo bloco estava copiado em cada tela, e copiado
 * significa que uma delas ia ficar para trás. */
export function Alert({ tone = "info", title, children, action }: Props) {
  const { box, mark } = TONES[tone];

  return (
    <div
      role={tone === "danger" || tone === "warn" ? "alert" : undefined}
      className={`animate-fade flex gap-3 rounded-dk px-4 py-3.5 ring-1 ring-inset ${box}`}
    >
      <span aria-hidden="true" className="mt-0.5 shrink-0 font-bold">
        {mark}
      </span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        <div className={title ? "mt-1 text-base" : "text-base"}>{children}</div>
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}
