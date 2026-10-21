import { useEffect, useState } from "react";

import { Button } from "./components/Button";
import { ThemeToggle } from "./components/ThemeToggle";
import { logout, restoreSession } from "./lib/api";
import type { SessionInfo } from "./lib/api";
import type { Plan } from "./lib/agro";
import { CompanyPage } from "./pages/CompanyPage";
import { ConsolidationPage } from "./pages/ConsolidationPage";
import { LoginPage } from "./pages/LoginPage";
import { NewPlanWizard } from "./pages/NewPlanWizard";
import { PlanDetailPage } from "./pages/PlanDetailPage";
import { PlansPage } from "./pages/PlansPage";

/* Navegação por estado, sem biblioteca de rotas: são três telas e o peso do pacote é
 * requisito, não detalhe. Quando houver deep link ou histórico a navegar, entra um
 * roteador — ver docs/ROADMAP.md. */
type View =
  | { name: "home" }
  | { name: "plans" }
  | { name: "company" }
  | { name: "consolidation" }
  | { name: "newPlan" }
  | { name: "plan"; plan: Plan };

export default function App() {
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>({ name: "home" });

  useEffect(() => {
    restoreSession()
      .then(setInfo)
      .finally(() => setChecking(false));
  }, []);

  if (checking) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-bg">
        <p className="text-lg text-ink-muted">Carregando…</p>
      </div>
    );
  }

  if (!info) {
    return <LoginPage onSignedIn={setInfo} />;
  }

  // O menu reflete o que a empresa tem instalado: sem permissão do módulo agro, a
  // pulverização simplesmente não aparece.
  // O menu vem dos módulos contratados, não do prefixo das permissões. O administrador
  // recebe as permissões de todos os módulos instalados na plataforma, então o prefixo
  // mostrava menu de módulo que a empresa não tem — e o servidor respondia 404.
  const hasAgro = info.active_modules.includes("agro");
  const canEditCompany = info.permissions.includes("core.tenant.update");

  return (
    <div className="min-h-dvh bg-bg">
      <header className="flex items-center justify-between gap-4 bg-brand px-6 py-4 text-white">
        <button
          type="button"
          onClick={() => setView({ name: "home" })}
          className="text-left"
        >
          <p className="text-xl font-bold tracking-tight">Decko</p>
          <p className="text-base text-white/70">{info.tenant.name}</p>
        </button>
        <p className="hidden text-base text-white/80 sm:block">{info.user.full_name}</p>
      </header>

      {view.name === "home" && (
        <main className="mx-auto max-w-2xl px-6 py-10">
          <h1 className="text-3xl font-bold text-ink">Olá, {info.user.full_name}</h1>

          {hasAgro ? (
            <button
              type="button"
              onClick={() => setView({ name: "plans" })}
              className="mt-6 w-full rounded-dk border border-line bg-surface px-6 py-6 text-left hover:border-brand-link"
            >
              <p className="text-2xl font-semibold text-ink">Pulverização</p>
              <p className="mt-1 text-lg text-ink-muted">
                Planejamentos operacionais, condição do tempo e relatório para o MAPA.
              </p>
            </button>
          ) : (
            <p className="mt-6 text-lg text-ink-muted">
              Nenhum módulo de negócio instalado ainda nesta empresa.
            </p>
          )}

          {canEditCompany && (
            <button
              type="button"
              onClick={() => setView({ name: "company" })}
              className="mt-4 w-full rounded-dk border border-line bg-surface px-6 py-5 text-left hover:border-brand-link"
            >
              <p className="text-xl font-semibold text-ink">Dados da empresa</p>
              <p className="mt-1 text-base text-ink-muted">
                Registro no MAPA, CREA e inscrições — o cabeçalho dos documentos.
              </p>
            </button>
          )}

          <div className="mt-10 flex flex-wrap items-center justify-between gap-4">
            <ThemeToggle />
            <div className="w-full sm:w-auto">
              <Button
                variant="ghost"
                onClick={() => {
                  void logout().then(() => {
                    setInfo(null);
                    setView({ name: "home" });
                  });
                }}
              >
                Sair
              </Button>
            </div>
          </div>
        </main>
      )}

      {view.name === "plans" && (
        <PlansPage
          onOpen={(plan) => setView({ name: "plan", plan })}
          onCreate={() => setView({ name: "newPlan" })}
          onConsolidate={() => setView({ name: "consolidation" })}
        />
      )}

      {view.name === "newPlan" && (
        <NewPlanWizard
          onCancel={() => setView({ name: "plans" })}
          onCreated={(plan) => setView({ name: "plan", plan })}
        />
      )}

      {view.name === "company" && <CompanyPage onBack={() => setView({ name: "home" })} />}

      {view.name === "consolidation" && (
        <ConsolidationPage onBack={() => setView({ name: "plans" })} />
      )}

      {view.name === "plan" && (
        <PlanDetailPage plan={view.plan} onBack={() => setView({ name: "plans" })} />
      )}
    </div>
  );
}
