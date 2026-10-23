import type { ReactNode } from "react";

import { Button } from "./Button";
import { Card, CardBody } from "./Card";

interface Props {
  steps: string[];
  current: number;
  children: ReactNode;
  onBack: () => void;
  onNext: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
  busy?: boolean;
}

/* Uma decisão por tela. É o que permite preencher um cadastro longo no celular, em pé no
 * meio da lavoura, sem treinamento. Ver docs/BRAND.md. */
export function Wizard({
  steps,
  current,
  children,
  onBack,
  onNext,
  nextLabel = "Continuar",
  nextDisabled = false,
  busy = false,
}: Props) {
  const isLast = current === steps.length - 1;

  return (
    <Card className="animate-rise overflow-hidden">
      {/* Trilha: número, nome do passo e barra. A barra sozinha não diz onde se está. */}
      <div className="border-b border-line-subtle bg-sunken px-5 py-5 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Passo {current + 1} de {steps.length}
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
          {steps[current]}
        </h2>

        <ol className="mt-4 flex gap-1.5">
          {steps.map((step, index) => (
            <li key={step} className="flex-1">
              <span
                aria-hidden="true"
                className={
                  "block h-1.5 rounded-full transition-colors duration-300 ease-dk " +
                  (index < current
                    ? "bg-action"
                    : index === current
                      ? "bg-action-bright"
                      : "bg-line")
                }
              />
              <span className="sr-only">
                {step}
                {index < current ? " (concluído)" : index === current ? " (atual)" : ""}
              </span>
            </li>
          ))}
        </ol>
      </div>

      <CardBody className="flex flex-col gap-5">{children}</CardBody>

      <footer className="flex flex-col-reverse gap-3 border-t border-line-subtle bg-sunken px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
        <Button inline variant="secondary" onClick={onBack} disabled={busy}>
          {current === 0 ? "Cancelar" : "Voltar"}
        </Button>
        <Button inline onClick={onNext} disabled={nextDisabled} loading={busy}>
          {isLast ? nextLabel : "Continuar"}
        </Button>
      </footer>
    </Card>
  );
}
