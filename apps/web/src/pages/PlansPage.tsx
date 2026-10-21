import { useEffect, useState } from "react";

import { Button } from "../components/Button";
import { agro } from "../lib/agro";
import type { Plan } from "../lib/agro";
import { dateBr, num } from "../lib/format";

interface Props {
  onOpen: (plan: Plan) => void;
  onCreate: () => void;
  onConsolidate: () => void;
}

export function PlansPage({ onOpen, onCreate, onConsolidate }: Props) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    agro
      .listPlans()
      .then(setPlans)
      .catch((cause) => {
        setPlans([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      });
  }, []);

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <h1 className="text-3xl font-bold text-ink">Planejamentos</h1>
      <p className="mt-1 text-lg text-ink-muted">
        Um por aplicação, como no talão.
      </p>

      <div className="mt-6 flex flex-col gap-3">
        <Button onClick={onCreate}>Novo planejamento</Button>
        {/* Ação de escritório, não de campo: fica abaixo da que se usa na lavoura. */}
        <Button variant="ghost" onClick={onConsolidate}>
          Fechamento do mês
        </Button>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-6 flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger"
        >
          <span aria-hidden="true" className="font-bold">
            !
          </span>
          {error}
        </p>
      )}

      {plans === null && <p className="mt-6 text-lg text-ink-muted">Carregando…</p>}

      {plans !== null && plans.length === 0 && !error && (
        <p className="mt-6 rounded-dk border border-line bg-surface px-5 py-6 text-lg text-ink-muted">
          Nenhum planejamento ainda. Crie o primeiro para registrar a aplicação e o tempo.
        </p>
      )}

      {plans !== null && plans.length > 0 && (
        <ul className="mt-6 flex flex-col gap-3">
          {plans.map((plan) => (
            <li key={plan.id}>
              <button
                type="button"
                onClick={() => onOpen(plan)}
                className="min-h-touch w-full rounded-dk border border-line bg-surface px-5 py-4 text-left hover:border-brand-link"
              >
                <p className="text-xl font-semibold text-ink">
                  Nº {plan.numero}
                  {plan.cultura ? ` · ${plan.cultura}` : ""}
                </p>
                <p className="text-base text-ink-muted">
                  {plan.data_aplicacao ? dateBr(plan.data_aplicacao) : "Sem data"}
                  {plan.area_ha ? ` · ${num(plan.area_ha)} ha` : ""} · {plan.status}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
