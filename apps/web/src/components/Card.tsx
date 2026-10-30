import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  /** Afunda o cartão: para blocos secundários que não devem disputar atenção. */
  muted?: boolean;
}

/* Superfície com elevação em vez de borda de 1px em tudo. A borda cinza uniforme é o que
 * dá à tela cara de formulário; a sombra em duas camadas dá profundidade sem peso. */
export function Card({ children, className = "", muted = false }: CardProps) {
  return (
    <section
      className={
        "rounded-lg " +
        (muted
          ? "bg-sunken ring-1 ring-line-subtle "
          : "bg-surface shadow-sm ring-1 ring-line-subtle ") +
        className
      }
    >
      {children}
    </section>
  );
}

interface CardHeaderProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function CardHeader({ title, description, action }: CardHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 px-5 pt-5 sm:px-6 sm:pt-6">
      <div className="min-w-0">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
      </div>
      {action}
    </header>
  );
}

export function CardBody({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={"px-5 py-5 sm:px-6 sm:py-6 " + className}>{children}</div>;
}

/* Linha de lista com separador fino. `last:border-0` evita a borda órfã no fim. */
export function Row({ children }: { children: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-line-subtle px-5 py-4 last:border-0 sm:px-6">
      {children}
    </li>
  );
}
