import type { ReactNode } from "react";

/** Identidade visual do módulo. É cor de reconhecimento, não de estado — ver
 *  docs/BRAND.md, seção 2.1. Os valores moram nos tokens; aqui só o nome do papel. */
export type Accent = "teal" | "blue" | "lime" | "violet" | "slate";

interface Props {
  title: string;
  description: string;
  icon: ReactNode;
  accent?: Accent;
  /** Com `onClick` a placa inteira vira botão. Sem, é um cartão com ação no rodapé. */
  onClick?: () => void;
  /** Etiqueta curta no canto, como "Instalado". */
  badge?: ReactNode;
  /** Linha de ação no pé do cartão, para quando a placa toda não é clicável. */
  footer?: ReactNode;
  /** Texto fino abaixo do título, como a versão do módulo. */
  meta?: string;
  disabled?: boolean;
  className?: string;
}

/* A placa de módulo: ícone à esquerda, título e descrição empilhados à direita.
 *
 * O mesmo componente serve ao início e à vitrine de aplicativos. Antes eram dois
 * cartões parecidos em arquivos diferentes, e "parecido" é o que fica desalinhado na
 * primeira alteração que passa só por um deles.
 *
 * O acabamento — translucidez, fio de luz, brilho do acento, escala do ícone — está em
 * `.dk-tile`, no styles.css, porque depende de pseudo-elemento e de `color-mix` com a
 * cor do acento. O que fica aqui é layout e conteúdo. */
export function ModuleTile({
  title,
  description,
  icon,
  accent = "slate",
  onClick,
  badge,
  footer,
  meta,
  disabled = false,
  className = "",
}: Props) {
  const corpo = (
    <>
      <div className="flex flex-1 items-start gap-4">
        <span
          aria-hidden="true"
          className="dk-tile__icon flex size-12 shrink-0 items-center justify-center rounded-lg text-xl"
        >
          {icon}
        </span>

        {/* Título e descrição empilhados ao lado do ícone, não embaixo dele: a leitura
            desce numa coluna só, e o cartão fica mais baixo na mesma grade. */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-lg font-semibold leading-snug tracking-tight text-ink">
              {title}
            </h3>
            {badge && <span className="shrink-0">{badge}</span>}
          </div>

          {meta && <p className="mt-0.5 text-xs tabular-nums text-ink-faint">{meta}</p>}

          <p className="mt-2 text-sm leading-relaxed text-ink-muted">{description}</p>
        </div>
      </div>

      {footer && <div className="mt-5">{footer}</div>}
    </>
  );

  const comum = `dk-tile animate-rise p-5 text-left sm:p-6 ${className}`;

  if (onClick) {
    return (
      <button
        type="button"
        data-accent={accent}
        onClick={onClick}
        disabled={disabled}
        className={`${comum} dk-tile--interactive w-full disabled:cursor-not-allowed disabled:opacity-60`}
      >
        {corpo}
      </button>
    );
  }

  return (
    <section data-accent={accent} className={comum}>
      {corpo}
    </section>
  );
}
