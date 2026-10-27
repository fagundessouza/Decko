import { useEffect, useState } from "react";

import { AppShell, Page, PageHeader } from "./components/AppShell";
import type { NavItem } from "./components/AppShell";
import { Alert } from "./components/Alert";
import { Card } from "./components/Card";
import { ModuleIcon } from "./components/ModuleIcon";
import { ModuleTile } from "./components/ModuleTile";
import { logout, renewSession, restoreSession } from "./lib/api";
import type { SessionInfo } from "./lib/api";
import type { Plan } from "./lib/agro";
import { comercial } from "./lib/comercial";
import type { Alertas, Produto } from "./lib/comercial";
import { AplicativosPage } from "./pages/AplicativosPage";
import { ChooseProfilePage } from "./pages/ChooseProfilePage";
import { ClientesPage } from "./pages/ClientesPage";
import { CompanyPage } from "./pages/CompanyPage";
import { ConferenciaPage } from "./pages/ConferenciaPage";
import { ConsolidationPage } from "./pages/ConsolidationPage";
import { LoginPage } from "./pages/LoginPage";
import { NewPlanWizard } from "./pages/NewPlanWizard";
import { NotaConferenciaPage } from "./pages/NotaConferenciaPage";
import { NotasPage } from "./pages/NotasPage";
import { NovoProdutoWizard } from "./pages/NovoProdutoWizard";
import { PdvPage } from "./pages/PdvPage";
import { PilotosPage } from "./pages/PilotosPage";
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
  | { name: "aplicativos" }
  | { name: "plans" }
  | { name: "company" }
  | { name: "consolidation" }
  | { name: "pilotos" }
  | { name: "newPlan" }
  | { name: "plan"; plan: Plan }
  | { name: "pdv" }
  | { name: "clientes" }
  | { name: "notas" }
  | { name: "nota"; notaId: string }
  | { name: "produtos" }
  | { name: "conferencia" }
  | { name: "novoProduto" }
  | { name: "produto"; produto: Produto }
  | { name: "unidades" };

/* A chave do menu que fica marcada em cada tela. Uma tela de detalhe mantém aceso o item
 * que levou até ela — perder a marcação ao navegar desorienta. */
const SECTION: Record<View["name"], string> = {
  home: "home",
  aplicativos: "aplicativos",
  plans: "agro",
  newPlan: "agro",
  plan: "agro",
  consolidation: "agro",
  pilotos: "agro",
  pdv: "pdv",
  clientes: "clientes",
  notas: "compras",
  nota: "compras",
  produtos: "comercial",
  conferencia: "comercial",
  novoProduto: "comercial",
  produto: "comercial",
  unidades: "comercial",
  company: "company",
};

export default function App() {
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>({ name: "home" });
  /* Empresa nova: a primeira tela é a escolha do ramo, mas quem prefere montar aplicativo
   * por aplicativo troca para a vitrine aqui mesmo, antes de existir menu. */
  const [montandoNaMao, setMontandoNaMao] = useState(false);

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
  const hasPdv = info.active_modules.includes("pdv");
  const hasCompras = info.active_modules.includes("compras");
  const hasClientes = info.active_modules.includes("clientes");
  const canEditCompany = info.permissions.includes("core.tenant.update");
  const canInstall = info.permissions.includes("core.module.activate");

  // A sessão é relida porque o menu depende dos módulos ativos, que acabaram de mudar no
  // servidor. Com token novo, porque instalar um aplicativo também concede permissões —
  // e as do token são as de quando ele foi emitido.
  const reloadSession = () => void renewSession().then(setInfo);

  // Empresa recém-criada não tem nada contratado. Em vez de uma tela vazia explicando que
  // está vazia, a primeira coisa é a escolha do ramo — ver ADR 0005.
  if (info.active_modules.length === 0 && canInstall) {
    return (
      <div className="min-h-dvh bg-bg">
        <header className="bg-brand-deep px-5 py-4 sm:px-8">
          <p className="text-lg font-bold tracking-tight text-white">Decko</p>
          <p className="text-sm text-white/60">{info.tenant.name}</p>
        </header>
        {montandoNaMao ? (
          <AplicativosPage onChanged={reloadSession} />
        ) : (
          <ChooseProfilePage
            onContracted={reloadSession}
            onBrowseApps={() => setMontandoNaMao(true)}
          />
        )}
      </div>
    );
  }

  const items: NavItem[] = [
    {
      key: "home",
      label: "Início",
      icon: <ModuleIcon name="home" size={22} />,
      onSelect: () => setView({ name: "home" }),
    },
  ];

  if (hasPdv) {
    items.push({
      key: "pdv",
      label: "Ponto de venda",
      icon: <ModuleIcon name="register" size={22} />,
      onSelect: () => setView({ name: "pdv" }),
    });
  }
  if (hasClientes) {
    items.push({
      key: "clientes",
      label: "Clientes",
      icon: <ModuleIcon name="people" size={22} />,
      onSelect: () => setView({ name: "clientes" }),
    });
  }
  if (hasCompras) {
    items.push({
      key: "compras",
      label: "Compras",
      icon: <ModuleIcon name="truck" size={22} />,
      onSelect: () => setView({ name: "notas" }),
    });
  }
  if (hasComercial) {
    items.push({
      key: "comercial",
      label: "Produtos e estoque",
      icon: <ModuleIcon name="boxes" size={22} />,
      onSelect: () => setView({ name: "produtos" }),
    });
  }
  if (hasAgro) {
    items.push({
      key: "agro",
      label: "Pulverização",
      icon: <ModuleIcon name="drone" size={22} />,
      onSelect: () => setView({ name: "plans" }),
    });
  }
  if (canInstall) {
    items.push({
      key: "aplicativos",
      label: "Aplicativos",
      icon: <ModuleIcon name="apps" size={22} />,
      onSelect: () => setView({ name: "aplicativos" }),
    });
  }
  if (canEditCompany) {
    items.push({
      key: "company",
      label: "Dados da empresa",
      icon: <ModuleIcon name="store" size={22} />,
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

          {hasComercial && (
            <AvisoDeEstoque onAbrir={() => setView({ name: "conferencia" })} />
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {hasPdv && (
              <ModuleTile
                title="Ponto de venda"
                description="Bipe o produto, receba em dinheiro, cartão ou pix e baixe o estoque."
                icon={<ModuleIcon name="register" />}
                accent="teal"
                onClick={() => setView({ name: "pdv" })}
              />
            )}
            {hasClientes && (
              <ModuleTile
                title="Clientes"
                description="Quem compra de você: pessoa ou empresa, com documento, contato e endereço."
                icon={<ModuleIcon name="people" />}
                accent="slate"
                onClick={() => setView({ name: "clientes" })}
              />
            )}
            {hasCompras && (
              <ModuleTile
                title="Compras"
                description="Importe o XML da nota do fornecedor e o estoque entra conferido."
                icon={<ModuleIcon name="truck" />}
                accent="violet"
                onClick={() => setView({ name: "notas" })}
              />
            )}
            {hasComercial && (
              <ModuleTile
                title="Produtos e estoque"
                description="Cadastro com unidade, caixa e fardo, lote e validade, entradas e saídas."
                icon={<ModuleIcon name="boxes" />}
                accent="blue"
                onClick={() => setView({ name: "produtos" })}
              />
            )}
            {hasAgro && (
              <ModuleTile
                title="Pulverização"
                description="Planejamentos operacionais, condição do tempo e relatório para o MAPA."
                icon={<ModuleIcon name="drone" />}
                accent="lime"
                onClick={() => setView({ name: "plans" })}
              />
            )}
            {canInstall && (
              <ModuleTile
                title="Aplicativos"
                description="Instale o que esta empresa precisa: ponto de venda, estoque, pulverização."
                icon={<ModuleIcon name="apps" />}
                accent="violet"
                onClick={() => setView({ name: "aplicativos" })}
              />
            )}
            {canEditCompany && (
              <ModuleTile
                title="Dados da empresa"
                description="Registro no MAPA, CREA e inscrições — o cabeçalho dos documentos."
                icon={<ModuleIcon name="store" />}
                accent="violet"
                onClick={() => setView({ name: "company" })}
              />
            )}
          </div>

          {!hasAgro && !hasComercial && !hasPdv && !hasCompras && !hasClientes && (
            <Card muted>
              <p className="px-6 py-8 text-base text-ink-muted">
                Nenhum aplicativo de negócio instalado ainda nesta empresa.
              </p>
            </Card>
          )}
        </Page>
      )}

      {view.name === "aplicativos" && <AplicativosPage onChanged={reloadSession} />}

      {view.name === "conferencia" && (
        <ConferenciaPage onBack={() => setView({ name: "home" })} />
      )}

      {view.name === "pdv" && <PdvPage onBack={() => setView({ name: "home" })} />}

      {view.name === "clientes" && (
        <ClientesPage onBack={() => setView({ name: "home" })} />
      )}

      {view.name === "notas" && (
        <NotasPage
          onBack={() => setView({ name: "home" })}
          onAbrir={(notaId) => setView({ name: "nota", notaId })}
        />
      )}

      {view.name === "nota" && (
        <NotaConferenciaPage
          notaId={view.notaId}
          onBack={() => setView({ name: "notas" })}
          onConfirmada={() => undefined}
        />
      )}

      {view.name === "plans" && (
        <PlansPage
          onOpen={(plan) => setView({ name: "plan", plan })}
          onCreate={() => setView({ name: "newPlan" })}
          onConsolidate={() => setView({ name: "consolidation" })}
          onPilotos={() => setView({ name: "pilotos" })}
        />
      )}

      {view.name === "newPlan" && (
        <NewPlanWizard
          onCancel={() => setView({ name: "plans" })}
          onCreated={(plan) => setView({ name: "plan", plan })}
        />
      )}

      {view.name === "pilotos" && <PilotosPage onBack={() => setView({ name: "plans" })} />}

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
          onConferencia={() => setView({ name: "conferencia" })}
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


/* O aviso de estoque na tela inicial.
 *
 * Não é um popup de propósito. Quem abre o Decko de manhã está abrindo o caixa, e um
 * modal na frente obriga a fechar algo antes de trabalhar — em uma semana a pessoa
 * aprende a clicar em "fechar" sem ler, e o aviso deixa de existir. Aqui ele fica no
 * caminho dos olhos, com o número à vista, e some sozinho quando não há o que avisar. */
function AvisoDeEstoque({ onAbrir }: { onAbrir: () => void }) {
  const [alertas, setAlertas] = useState<Alertas | null>(null);

  useEffect(() => {
    // Falha em silêncio: o aviso é um extra na tela inicial, e derrubá-la por causa dele
    // seria pior do que não avisar.
    comercial.alertas().then(setAlertas).catch(() => undefined);
  }, []);

  if (!alertas || alertas.total === 0) return null;

  const acabando = alertas.acabando.length;
  const vencendo = alertas.vencendo.length;
  const partes = [
    acabando > 0 && `${acabando} ${acabando === 1 ? "produto acabando" : "produtos acabando"}`,
    vencendo > 0 && `${vencendo} ${vencendo === 1 ? "lote vencendo" : "lotes vencendo"}`,
  ].filter(Boolean);

  return (
    <div className="mb-6">
      <Alert tone="warn">
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{partes.join(" e ")}.</span>
          <button
            type="button"
            onClick={onAbrir}
            className="font-semibold text-brand-link underline-offset-2 hover:underline"
          >
            Conferir
          </button>
        </span>
      </Alert>
    </div>
  );
}
