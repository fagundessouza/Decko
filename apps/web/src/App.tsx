import { useEffect, useState } from "react";

import { AppShell, Page, PageHeader } from "./components/AppShell";
import type { NavItem } from "./components/AppShell";
import { Card } from "./components/Card";
import { fetchSession, logout, restoreSession } from "./lib/api";
import type { SessionInfo } from "./lib/api";
import type { Plan } from "./lib/agro";
import type { Produto } from "./lib/comercial";
import { ChooseProfilePage } from "./pages/ChooseProfilePage";
import { CompanyPage } from "./pages/CompanyPage";
import { ConsolidationPage } from "./pages/ConsolidationPage";
import { LoginPage } from "./pages/LoginPage";
import { NewPlanWizard } from "./pages/NewPlanWizard";
import { NovoProdutoWizard } from "./pages/NovoProdutoWizard";
import { PlanDetailPage } from "./pages/PlanDetailPage";
import { PlansPage } from "./pages/PlansPage";
import { ProdutoDetailPage } from "./pages/ProdutoDetailPage";
import { ProdutosPage } from "./pages/ProdutosPage";
import { UnidadesPage } from "./pages/UnidadesPage";

/* Navegação por estado, sem biblioteca de rotas: o peso do pacote é requisito, não
 * detalhe. Quando houver deep link ou histórico a navegar, entra um roteador — ver
 * docs/ROADMAP.md. */
type View =
  | { name: "home" }
  | { name: "plans" }
  | { name: "company" }
  | { name: "consolidation" }
  | { name: "newPlan" }
  | { name: "plan"; plan: Plan }
  | { name: "produtos" }
  | { name: "novoProduto" }
  | { name: "produto"; produto: Produto }
  | { name: "unidades" };

/* A chave do menu que fica marcada em cada tela. Uma tela de detalhe mantém aceso o item
 * que levou até ela — perder a marcação ao navegar desorienta. */
const SECTION: Record<View["name"], string> = {
  home: "home",
  plans: "agro",
  newPlan: "agro",
  plan: "agro",
  consolidation: "agro",
  produtos: "comercial",
  novoProduto: "comercial",
  produto: "comercial",
  unidades: "comercial",
  company: "company",
};

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
        <p className="animate-fade text-base text-ink-muted">Carregando…</p>
      </div>
    );
  }

  if (!info) {
    return <LoginPage onSignedIn={setInfo} />;
  }

  // O menu vem dos módulos contratados, não do prefixo das permissões. O administrador
  // recebe as permissões de todos os módulos instalados na plataforma, então o prefixo
  // mostrava menu de módulo que a empresa não tem — e o servidor respondia 404.
  const hasAgro = info.active_modules.includes("agro");
  const hasComercial = info.active_modules.includes("comercial");
  const canEditCompany = info.permissions.includes("core.tenant.update");

  // Empresa recém-criada não tem nada contratado. Em vez de uma tela vazia explicando que
  // está vazia, a primeira coisa é a escolha do ramo — ver ADR 0005.
  if (info.active_modules.length === 0 && info.permissions.includes("core.module.activate")) {
    return (
      <div className="min-h-dvh bg-bg">
        <header className="bg-brand-deep px-5 py-4 sm:px-8">
          <p className="text-lg font-bold tracking-tight text-white">Decko</p>
          <p className="text-sm text-white/60">{info.tenant.name}</p>
        </header>
        <ChooseProfilePage
          onContracted={() => {
            // A sessão é relida porque o menu depende dos módulos ativos, que acabaram
            // de mudar no servidor.
            void fetchSession().then(setInfo);
          }}
        />
      </div>
    );
  }

  const items: NavItem[] = [
    {
      key: "home",
      label: "Início",
      icon: "◆",
      onSelect: () => setView({ name: "home" }),
    },
  ];

  if (hasComercial) {
    items.push({
      key: "comercial",
      label: "Produtos e estoque",
      icon: "▣",
      onSelect: () => setView({ name: "produtos" }),
    });
  }
  if (hasAgro) {
    items.push({
      key: "agro",
      label: "Pulverização",
      icon: "✦",
      onSelect: () => setView({ name: "plans" }),
    });
  }
  if (canEditCompany) {
    items.push({
      key: "company",
      label: "Dados da empresa",
      icon: "⚙",
      onSelect: () => setView({ name: "company" }),
    });
  }

  return (
    <AppShell
      tenantName={info.tenant.name}
      userName={info.user.full_name}
      items={items}
      activeKey={SECTION[view.name]}
      onHome={() => setView({ name: "home" })}
      onSignOut={() => {
        void logout().then(() => {
          setInfo(null);
          setView({ name: "home" });
        });
      }}
    >
      {view.name === "home" && (
        <Page wide>
          <PageHeader
            title={`Olá, ${info.user.full_name.split(" ")[0]}`}
            description="Escolha por onde começar."
          />

          <div className="grid gap-4 sm:grid-cols-2">
            {hasComercial && (
              <ModuleCard
                title="Produtos e estoque"
                description="Cadastro com unidade, caixa e fardo, lote e validade, entradas e saídas."
                icon="▣"
                onClick={() => setView({ name: "produtos" })}
              />
            )}
            {hasAgro && (
              <ModuleCard
                title="Pulverização"
                description="Planejamentos operacionais, condição do tempo e relatório para o MAPA."
                icon="✦"
                onClick={() => setView({ name: "plans" })}
              />
            )}
            {canEditCompany && (
              <ModuleCard
                title="Dados da empresa"
                description="Registro no MAPA, CREA e inscrições — o cabeçalho dos documentos."
                icon="⚙"
                onClick={() => setView({ name: "company" })}
              />
            )}
          </div>

          {!hasAgro && !hasComercial && (
            <Card muted>
              <p className="px-6 py-8 text-base text-ink-muted">
                Nenhum módulo de negócio instalado ainda nesta empresa.
              </p>
            </Card>
          )}
        </Page>
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

      {view.name === "produtos" && (
        <ProdutosPage
          onBack={() => setView({ name: "home" })}
          onOpen={(produto) => setView({ name: "produto", produto })}
          onNew={() => setView({ name: "novoProduto" })}
          onUnidades={() => setView({ name: "unidades" })}
        />
      )}

      {view.name === "novoProduto" && (
        <NovoProdutoWizard
          onCancel={() => setView({ name: "produtos" })}
          onCreated={(produto) => setView({ name: "produto", produto })}
        />
      )}

      {view.name === "produto" && (
        <ProdutoDetailPage
          produto={view.produto}
          onBack={() => setView({ name: "produtos" })}
        />
      )}

      {view.name === "unidades" && (
        <UnidadesPage onBack={() => setView({ name: "produtos" })} />
      )}
    </AppShell>
  );
}

function ModuleCard({
  title,
  description,
  icon,
  onClick,
}: {
  title: string;
  description: string;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group animate-rise rounded-lg bg-surface p-6 text-left shadow-sm ring-1 ring-line-subtle
                 transition-[box-shadow,transform] duration-200 ease-dk
                 hover:-translate-y-0.5 hover:shadow-md"
    >
      <span
        aria-hidden="true"
        className="flex size-11 items-center justify-center rounded-dk bg-brand-soft text-lg text-brand-link
                   transition-colors duration-200 ease-dk group-hover:bg-brand-link group-hover:text-white"
      >
        {icon}
      </span>
      <p className="mt-4 text-lg font-semibold text-ink">{title}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{description}</p>
    </button>
  );
}
