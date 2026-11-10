import { lazy, Suspense, useEffect, useState } from "react";

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
import { TrocarEmpresa } from "./components/TrocarEmpresa";
import { LoginPage } from "./pages/LoginPage";

/* Cada tela entra sob demanda, e não no pacote de abertura.
 *
 * O sistema é modular por empresa: quem contratou só o cadastro de clientes não tem
 * motivo para baixar o wizard do agro, o ponto de venda e a consolidação mensal. Até
 * aqui baixava — tudo estava no mesmo arquivo. Peso é requisito funcional neste projeto,
 * e esta é a única economia que cresce junto com o catálogo de módulos.
 *
 * A LoginPage fica de fora: é a primeira coisa que aparece, e buscá-la à parte
 * acrescentaria uma viagem de rede no pior momento possível.
 *
 * São exportações nomeadas, daí o `.then` — `lazy` espera `default`. */
const AplicativosPage = lazy(() =>
  import("./pages/AplicativosPage").then((m) => ({ default: m.AplicativosPage })),
);
const AssinaturasPage = lazy(() =>
  import("./pages/AssinaturasPage").then((m) => ({ default: m.AssinaturasPage })),
);
const MeuCaixaPage = lazy(() =>
  import("./pages/MeuCaixaPage").then((m) => ({ default: m.MeuCaixaPage })),
);
const CaixaPage = lazy(() =>
  import("./pages/CaixaPage").then((m) => ({ default: m.CaixaPage })),
);
const DevolucaoPage = lazy(() =>
  import("./pages/DevolucaoPage").then((m) => ({ default: m.DevolucaoPage })),
);
const ChooseProfilePage = lazy(() =>
  import("./pages/ChooseProfilePage").then((m) => ({ default: m.ChooseProfilePage })),
);
const ClientesPage = lazy(() =>
  import("./pages/ClientesPage").then((m) => ({ default: m.ClientesPage })),
);
const CompanyPage = lazy(() =>
  import("./pages/CompanyPage").then((m) => ({ default: m.CompanyPage })),
);
const ContasPage = lazy(() =>
  import("./pages/ContasPage").then((m) => ({ default: m.ContasPage })),
);
const ConferenciaPage = lazy(() =>
  import("./pages/ConferenciaPage").then((m) => ({ default: m.ConferenciaPage })),
);
const ConsolidationPage = lazy(() =>
  import("./pages/ConsolidationPage").then((m) => ({ default: m.ConsolidationPage })),
);
const NewPlanWizard = lazy(() =>
  import("./pages/NewPlanWizard").then((m) => ({ default: m.NewPlanWizard })),
);
const NotaConferenciaPage = lazy(() =>
  import("./pages/NotaConferenciaPage").then((m) => ({ default: m.NotaConferenciaPage })),
);
const NotasPage = lazy(() =>
  import("./pages/NotasPage").then((m) => ({ default: m.NotasPage })),
);
const NovoProdutoWizard = lazy(() =>
  import("./pages/NovoProdutoWizard").then((m) => ({ default: m.NovoProdutoWizard })),
);
const PdvPage = lazy(() =>
  import("./pages/PdvPage").then((m) => ({ default: m.PdvPage })),
);
const PilotosPage = lazy(() =>
  import("./pages/PilotosPage").then((m) => ({ default: m.PilotosPage })),
);
const PlanDetailPage = lazy(() =>
  import("./pages/PlanDetailPage").then((m) => ({ default: m.PlanDetailPage })),
);
const PlansPage = lazy(() =>
  import("./pages/PlansPage").then((m) => ({ default: m.PlansPage })),
);
const ProdutoDetailPage = lazy(() =>
  import("./pages/ProdutoDetailPage").then((m) => ({ default: m.ProdutoDetailPage })),
);
const ProdutosPage = lazy(() =>
  import("./pages/ProdutosPage").then((m) => ({ default: m.ProdutosPage })),
);
const TrilhaPage = lazy(() =>
  import("./pages/TrilhaPage").then((m) => ({ default: m.TrilhaPage })),
);
const UnidadesPage = lazy(() =>
  import("./pages/UnidadesPage").then((m) => ({ default: m.UnidadesPage })),
);

/* Navegação por estado, sem biblioteca de rotas: o peso do pacote é requisito, não
 * detalhe. Quando houver deep link ou histórico a navegar, entra um roteador — ver
 * docs/ROADMAP.md. */
type View =
  | { name: "home" }
  | { name: "aplicativos" }
  | { name: "plans" }
  | { name: "company" }
  | { name: "trilha" }
  | { name: "consolidation" }
  | { name: "pilotos" }
  | { name: "newPlan" }
  | { name: "plan"; plan: Plan }
  | { name: "pdv" }
  | { name: "clientes" }
  | { name: "contas" }
  | { name: "assinaturas" }
  | { name: "notas" }
  | { name: "nota"; notaId: string }
  | { name: "produtos" }
  | { name: "caixa" }
  | { name: "meu-caixa" }
  | { name: "devolucao" }
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
  contas: "financeiro",
  assinaturas: "assinaturas",
  notas: "compras",
  nota: "compras",
  produtos: "comercial",
  caixa: "caixa",
  "meu-caixa": "meu-caixa",
  devolucao: "devolucao",
  conferencia: "comercial",
  novoProduto: "comercial",
  produto: "comercial",
  unidades: "comercial",
  company: "company",
  trilha: "trilha",
};

export default function App() {
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>({ name: "home" });
  /* Empresa nova: a primeira tela é a escolha do ramo, mas quem prefere montar aplicativo
   * por aplicativo troca para a vitrine aqui mesmo, antes de existir menu. */
  const [montandoNaMao, setMontandoNaMao] = useState(false);
  const [trocando, setTrocando] = useState(false);

  useEffect(() => {
    restoreSession()
      .then(setInfo)
      .finally(() => setChecking(false));
  }, []);

  /* Busca o pedaço do PDV assim que a sessão existe, se a empresa tiver o módulo.
   *
   * Carregar sob demanda troca peso de abertura por uma espera na primeira visita a cada
   * tela. Em quase toda tela isso é invisível; no caixa não é, porque lá há fila. Baixar
   * em segundo plano logo depois de entrar põe essa espera onde ninguém a vê. */
  useEffect(() => {
    if (info?.active_modules.includes("pdv")) void import("./pages/PdvPage");
  }, [info]);

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
  const hasFinanceiro = info.active_modules.includes("financeiro");
  const hasAssinaturas = info.active_modules.includes("assinaturas");
  const canEditCompany = info.permissions.includes("core.tenant.update");
  const canInstall = info.permissions.includes("core.module.activate");
  const canReadAudit = info.permissions.includes("core.audit.read");

  // A sessão é relida porque o menu depende dos módulos ativos, que acabaram de mudar no
  // servidor. Com token novo, porque instalar um aplicativo também concede permissões —
  // e as do token são as de quando ele foi emitido.
  const reloadSession = () => void renewSession().then(setInfo);

  // Empresa recém-criada não tem nada contratado. Em vez de uma tela vazia explicando que
  // está vazia, a primeira coisa é a escolha do ramo — ver ADR 0005.
  if (info.active_modules.length === 0 && canInstall) {
    return (
      <div className="min-h-dvh bg-bg">
        {/* Esta tela não tem o menu lateral, e por isso precisa das duas saídas aqui: sem
            elas, quem entra numa empresa sem módulo nenhum fica preso na escolha do ramo —
            sem como sair e sem como voltar para a empresa de onde veio. */}
        <header className="flex flex-wrap items-center justify-between gap-3 bg-brand-deep px-5 py-4 sm:px-8">
          <div className="min-w-0">
            <p className="text-lg font-bold tracking-tight text-white">Decko</p>
            <p className="truncate text-sm text-white/60">{info.tenant.name}</p>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setTrocando(true)}
              className="min-h-touch rounded-dk px-3 text-base text-white/70 hover:bg-white/5 hover:text-white"
            >
              Trocar de empresa
            </button>
            <button
              type="button"
              onClick={() => {
                void logout().then(() => {
                  setInfo(null);
                  setView({ name: "home" });
                });
              }}
              className="min-h-touch rounded-dk px-3 text-base text-white/70 hover:bg-white/5 hover:text-white"
            >
              Sair
            </button>
          </div>
        </header>
        {montandoNaMao ? (
          <AplicativosPage onChanged={reloadSession} />
        ) : (
          <ChooseProfilePage
            onContracted={reloadSession}
            onBrowseApps={() => setMontandoNaMao(true)}
          />
        )}

        <TrocarEmpresa
          open={trocando}
          slugAtual={info.tenant.slug}
          emailAtual={info.user.email}
          onClose={() => setTrocando(false)}
          onTrocado={(nova) => {
            setTrocando(false);
            setInfo(nova);
            setMontandoNaMao(false);
            setView({ name: "home" });
          }}
        />
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
    // Vender é a tela principal; caixa, devolução e conferência são do mesmo módulo e
    // ficam dentro dela. Quatro itens irmãos com o mesmo ícone pareciam quatro módulos.
    items.push({
      key: "pdv",
      label: "Ponto de venda",
      icon: <ModuleIcon name="register" size={22} />,
      onSelect: () => setView({ name: "pdv" }),
      children: [
        {
          key: "meu-caixa",
          label: "Meu caixa",
          icon: null,
          onSelect: () => setView({ name: "meu-caixa" }),
        },
        {
          key: "devolucao",
          label: "Devolução de venda",
          icon: null,
          onSelect: () => setView({ name: "devolucao" }),
        },
        {
          key: "caixa",
          label: "Conferência de caixa",
          icon: null,
          onSelect: () => setView({ name: "caixa" }),
        },
      ],
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
  if (hasFinanceiro) {
    items.push({
      key: "financeiro",
      label: "Contas de recebimento",
      icon: <ModuleIcon name="bank" size={22} />,
      onSelect: () => setView({ name: "contas" }),
    });
  }
  if (hasAssinaturas) {
    items.push({
      key: "assinaturas",
      label: "Assinaturas",
      icon: <ModuleIcon name="card" size={22} />,
      onSelect: () => setView({ name: "assinaturas" }),
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
  if (canReadAudit) {
    items.push({
      key: "trilha",
      label: "Trilha de auditoria",
      icon: <ModuleIcon name="shield" size={22} />,
      onSelect: () => setView({ name: "trilha" }),
    });
  }

  return (
    <AppShell
      tenantName={info.tenant.name}
      userName={info.user.full_name}
      items={items}
      activeKey={SECTION[view.name]}
      onHome={() => setView({ name: "home" })}
      onSwitchCompany={() => setTrocando(true)}
      onSignOut={() => {
        void logout().then(() => {
          setInfo(null);
          setView({ name: "home" });
        });
      }}
    >
      <Suspense
        fallback={
          <Page>
            <p className="animate-fade text-base text-ink-muted">Carregando…</p>
          </Page>
        }
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

      {view.name === "meu-caixa" && <MeuCaixaPage onBack={() => setView({ name: "home" })} />}

      {view.name === "caixa" && <CaixaPage onBack={() => setView({ name: "home" })} />}

      {view.name === "devolucao" && <DevolucaoPage onBack={() => setView({ name: "home" })} />}

      {view.name === "conferencia" && (
        <ConferenciaPage onBack={() => setView({ name: "home" })} />
      )}

      {view.name === "pdv" && (
        <PdvPage
          onBack={() => setView({ name: "home" })}
          empresa={info.tenant.name}
          podeIdentificar={hasClientes && info.permissions.includes("pdv.venda.identificar")}
        />
      )}

      {view.name === "clientes" && (
        <ClientesPage onBack={() => setView({ name: "home" })} />
      )}

      {view.name === "contas" && <ContasPage onBack={() => setView({ name: "home" })} />}
      {view.name === "assinaturas" && (
        <AssinaturasPage onBack={() => setView({ name: "home" })} />
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

      {view.name === "trilha" && <TrilhaPage onBack={() => setView({ name: "home" })} />}

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

      <TrocarEmpresa
        open={trocando}
        slugAtual={info.tenant.slug}
        emailAtual={info.user.email}
        onClose={() => setTrocando(false)}
        onTrocado={(nova) => {
          setTrocando(false);
          setInfo(nova);
          // A empresa nova tem outros módulos e outras permissões: ficar na tela anterior
          // levaria a um 404 do servidor ou a um menu que não combina com o que se vê.
          setView({ name: "home" });
        }}
      />
      </Suspense>
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
