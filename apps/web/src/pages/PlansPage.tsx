import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, Row } from "../components/Card";
import type { Plan } from "../lib/agro";
import { EVENTO_FILA } from "../lib/fila";
import { dateBr, num } from "../lib/format";
import { listarPlanos } from "../lib/lavoura";
import { session } from "../lib/session";

interface Props {
  onOpen: (plan: Plan) => void;
  onCreate: () => void;
  onConsolidate: () => void;
  onPilotos: () => void;
  /** A importação do registro de voo do equipamento. */
  onImportarVoos: () => void;
}

const STATUS_TONE: Record<string, "neutral" | "info" | "success"> = {
  rascunho: "neutral",
  concluido: "info",
  assinado: "success",
  enviado: "success",
};

export function PlansPage({
  onOpen,
  onCreate,
  onConsolidate,
  onPilotos,
  onImportarVoos,
}: Props) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  /* Os que ainda não chegaram ao servidor, e os que ele recusou. Sem isto, o planejamento
   * preenchido na lavoura apareceria igual aos outros e o piloto iria embora achando que
   * o documento já existe — ver a fatia 6 da ADR 0022. */
  const [pendentes, setPendentes] = useState<Set<string>>(new Set());
  const [recusados, setRecusados] = useState<Map<string, string>>(new Map());
  const [doCache, setDoCache] = useState(false);
  const empresa = session.getTenantSlug();

  function recarregar() {
    return listarPlanos(empresa)
      .then((visao) => {
        setPlans(visao.planos);
        setPendentes(visao.pendentes);
        setRecusados(visao.recusados);
        setDoCache(visao.doCache);
        setError(null);
      })
      .catch((cause) => {
        setPlans([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      });
  }

  useEffect(() => {
    void recarregar();
  }, []);

  /* A fila sobe sozinha em segundo plano; quando isso acontece, a tela precisa parar de
   * dizer "esperando a rede" sem a pessoa recarregar nada. */
  useEffect(() => {
    const atualizar = () => void recarregar();
    window.addEventListener(EVENTO_FILA, atualizar);
    return () => window.removeEventListener(EVENTO_FILA, atualizar);
  });

  return (
    <Page wide>
      <PageHeader
        title="Planejamentos"
        description="Um por aplicação, como no talão."
        action={
          <div className="flex gap-2">
            {/* Ações de escritório, não de campo: ficam depois da que se usa na lavoura. */}
            {/* Antes de "Novo planejamento" de propósito: quem volta do campo tem o
                arquivo de voos na mão, e preencher à mão é o que esta tela evita. */}
            <Button inline variant="secondary" onClick={onImportarVoos}>
              Importar voos
            </Button>
            <Button inline variant="secondary" onClick={onPilotos}>
              Pilotos
            </Button>
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

      {doCache && (
        <div className="mb-6">
          <Alert tone="warn">
            Sem conexão: esta lista é a que está guardada neste aparelho. Dá para criar
            planejamento — ele sobe sozinho quando a rede voltar, e é lá que o número do
            documento nasce.
          </Alert>
        </div>
      )}

      {[...recusados].map(([id, motivo]) => (
        <div className="mb-6" key={id}>
          <Alert tone="danger">
            Um planejamento deste aparelho não foi aceito pelo servidor: {motivo} Ele
            continua guardado aqui.
          </Alert>
        </div>
      ))}

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
                    {plan.numero ?? "—"}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-ink">
                      {plan.numero === null ? "Sem número ainda" : `Nº ${plan.numero}`}
                      {plan.cultura ? ` · ${plan.cultura}` : ""}
                    </span>
                    <span className="block truncate text-sm text-ink-muted">
                      {plan.data_aplicacao ? dateBr(plan.data_aplicacao) : "Sem data"}
                      {plan.area_ha ? ` · ${num(plan.area_ha)} ha` : ""}
                    </span>
                  </span>
                </button>

                <div className="flex shrink-0 items-center gap-3">
                  {pendentes.has(plan.id) && <Badge tone="warn">esperando a rede</Badge>}
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
