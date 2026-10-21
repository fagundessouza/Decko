import type { ReactNode } from "react";

import { Button } from "./Button";

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
 * meio da lavoura, sem treinamento. Ver docs/BRAND.md, seção 6. */
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
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-base text-ink-muted">
          Passo {current + 1} de {steps.length}
        </p>
        <h2 className="mt-1 text-2xl font-bold text-ink">{steps[current]}</h2>

        {/* Barra de progresso com rótulo textual: cor sozinha não informa. */}
        <div className="mt-3 flex gap-1.5" aria-hidden="true">
          {steps.map((step, index) => (
            <span
              key={step}
              className={
                "h-1.5 flex-1 rounded-full " +
                (index <= current ? "bg-action" : "bg-line")
              }
            />
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-5">{children}</div>

      <div className="flex flex-col gap-3 sm:flex-row-reverse">
        <Button onClick={onNext} disabled={nextDisabled} loading={busy}>
          {isLast ? nextLabel : "Continuar"}
        </Button>
        <Button variant="ghost" onClick={onBack} disabled={busy}>
          {current === 0 ? "Cancelar" : "Voltar"}
        </Button>
      </div>
    </div>
  );
}
