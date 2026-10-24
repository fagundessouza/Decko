import type { ReactNode } from "react";

type Tone = "neutral" | "info" | "success" | "warn" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-muted ring-line",
  info: "bg-brand-soft text-ink ring-brand-link/20",
  success: "bg-action-soft text-ink ring-action/25",
  warn: "bg-warn-soft text-ink ring-warn/30",
  danger: "bg-danger-soft text-danger ring-danger/25",
};

interface Props {
  tone?: Tone;
  /** Símbolo à esquerda. Alerta nunca é comunicado só por cor — ver docs/BRAND.md. */
  icon?: ReactNode;
  children: ReactNode;
}

export function Badge({ tone = "neutral", icon, children }: Props) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium " +
        `ring-1 ring-inset ${TONES[tone]}`
      }
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}
