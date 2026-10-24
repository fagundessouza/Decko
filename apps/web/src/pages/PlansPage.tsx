import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, Row } from "../components/Card";
import { agro } from "../lib/agro";
import type { Plan } from "../lib/agro";
import { dateBr, num } from "../lib/format";

interface Props {
  onOpen: (plan: Plan) => void;
  onCreate: () => void;
  onConsolidate: () => void;
}

const STATUS_TONE: Record<string, "neutral" | "info" | "success"> = {
  rascunho: "neutral",
  concluido: "info",
  assinado: "success",
  enviado: "success",
};

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
    <Page wide>
      <PageHeader
        title="Planejamentos"
        description="Um por aplicação, como no talão."
        action={
          <div className="flex gap-2">
            {/* Ação de escritório, não de campo: fica depois da que se usa na lavoura. */}
            <Button inline variant="secondary" onClick={onConsolidate}>
              Fechamento do mês
            </Button>
            <Button inline onClick={onCreate}>
              Novo planejamento
            </Button>
          </div>
        }
      />

      {error && (
        <div className="mb-6">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}

      {plans === null && (
        <p className="animate-fade text-base text-ink-muted">Carregando…</p>
      )}

      {plans !== null && plans.length === 0 && !error && (
        <Card muted>
          <div className="px-6 py-10 text-center">
            <p className="text-base text-ink-muted">
              Nenhum planejamento ainda. Crie o primeiro para registrar a aplicação e o
              tempo.
            </p>
            <div className="mx-auto mt-5 max-w-xs">
              <Button onClick={onCreate}>Novo planejamento</Button>
            </div>
          </div>
        </Card>
      )}

      {plans !== null && plans.length > 0 && (
        <Card>
          <ul>
            {plans.map((plan) => (
              <Row key={plan.id}>
                <button
                  type="button"
                  onClick={() => onOpen(plan)}
                  className="-m-1 flex min-w-0 flex-1 items-center gap-4 rounded-dk p-1 text-left"
                >
                  <span
                    aria-hidden="true"
                    className="tabular hidden size-10 shrink-0 items-center justify-center rounded-dk bg-brand-soft text-sm font-semibold text-brand-link sm:flex"
                  >
                    {plan.numero}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-ink">
                      Nº {plan.numero}
                      {plan.cultura ? ` · ${plan.cultura}` : ""}
                    </span>
                    <span className="block truncate text-sm text-ink-muted">
                      {plan.data_aplicacao ? dateBr(plan.data_aplicacao) : "Sem data"}
                      {plan.area_ha ? ` · ${num(plan.area_ha)} ha` : ""}
                    </span>
                  </span>
                </button>

                <div className="flex shrink-0 items-center gap-3">
                  <Badge tone={STATUS_TONE[plan.status] ?? "neutral"}>{plan.status}</Badge>
                  <span aria-hidden="true" className="text-ink-faint">
                    ›
                  </span>
                </div>
              </Row>
            ))}
          </ul>
        </Card>
      )}
    </Page>
  );
}
