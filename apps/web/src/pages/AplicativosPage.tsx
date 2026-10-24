import { useEffect, useMemo, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Modal } from "../components/Modal";
import { TextField } from "../components/TextField";
import { platform } from "../lib/profiles";
import type { Module } from "../lib/profiles";

interface Props {
  /** Chamado depois de instalar ou desinstalar: o menu depende dos módulos ativos. */
  onChanged: () => void;
}

/* A vitrine de aplicativos.
 *
 * O catálogo inteiro vem do servidor, que o lê dos manifestos em disco. Nada aqui é uma
 * lista escrita à mão: acrescentar um módulo ao produto é escrever o module.toml dele, e
 * esta tela passa a mostrá-lo sem alteração nenhuma. */
export function AplicativosPage({ onChanged }: Props) {
  const [modules, setModules] = useState<Module[] | null>(null);
  const [busca, setBusca] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState<Module | null>(null);

  function recarregar() {
    return platform
      .listModules()
      .then(setModules)
      .catch((cause) => {
        setModules([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      });
  }

  useEffect(() => {
    void recarregar();
  }, []);

  async function instalar(module: Module) {
    setBusy(module.name);
    setError(null);
    try {
      await platform.activateModule(module.name);
      await recarregar();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível instalar.");
    } finally {
      setBusy(null);
    }
  }

  async function desinstalar(module: Module) {
    setBusy(module.name);
    setError(null);
    setConfirmar(null);
    try {
      await platform.deactivateModule(module.name);
      await recarregar();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível desinstalar.");
    } finally {
      setBusy(null);
    }
  }

  /* Agrupado por categoria, e os módulos em ordem alfabética dentro de cada uma. */
  const grupos = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    const filtrados = (modules ?? []).filter(
      (module) =>
        termo === "" ||
        module.label.toLowerCase().includes(termo) ||
        module.summary.toLowerCase().includes(termo) ||
        module.category.toLowerCase().includes(termo),
    );

    const porCategoria = new Map<string, Module[]>();
    for (const module of filtrados) {
      const atual = porCategoria.get(module.category) ?? [];
      atual.push(module);
      porCategoria.set(module.category, atual);
    }
    for (const lista of porCategoria.values()) {
      lista.sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
    }
    return [...porCategoria.entries()];
  }, [modules, busca]);

  const porNome = useMemo(
    () => new Map((modules ?? []).map((module) => [module.name, module])),
    [modules],
  );

  const instalados = (modules ?? []).filter((module) => module.active).length;

  return (
    <Page wide>
      <PageHeader
        title="Aplicativos"
        description={
          modules === null
            ? "Carregando o catálogo…"
            : `${instalados} de ${modules.length} instalados nesta empresa.`
        }
      />

      {error && (
        <div className="mb-6">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}

      <div className="mb-8 max-w-md">
        <TextField
          label="Procurar"
          leading="⌕"
          placeholder="Nome ou o que o aplicativo faz"
          value={busca}
          onChange={(event) => setBusca(event.target.value)}
        />
      </div>

      {modules !== null && grupos.length === 0 && (
        <Card muted>
          <p className="px-6 py-10 text-center text-base text-ink-muted">
            {busca.trim() === ""
              ? "Nenhum aplicativo instalado nesta plataforma ainda."
              : "Nenhum aplicativo encontrado para essa busca."}
          </p>
        </Card>
      )}

      <div className="flex flex-col gap-10">
        {grupos.map(([categoria, lista]) => (
          <section key={categoria}>
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-faint">
              {categoria}
            </h2>

            <ul className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {lista.map((module) => (
                <li key={module.name} className="flex">
                  <AppCard
                    module={module}
                    dependencias={module.depends
                      .map((name) => porNome.get(name))
                      .filter((item): item is Module => item !== undefined)
                      .filter((item) => !item.required && !item.active)}
                    busy={busy === module.name}
                    onInstalar={() => void instalar(module)}
                    onDesinstalar={() => setConfirmar(module)}
                  />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <Modal
        open={confirmar !== null}
        title={`Desinstalar ${confirmar?.label ?? ""}?`}
        description="As telas somem do menu desta empresa."
        onClose={() => setConfirmar(null)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setConfirmar(null)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              inline
              onClick={() => confirmar && void desinstalar(confirmar)}
            >
              Desinstalar
            </Button>
          </div>
        }
      >
        <p className="text-base leading-relaxed text-ink-muted">
          Nada é apagado. O que já foi lançado continua no banco e volta a aparecer se o
          aplicativo for instalado de novo.
        </p>
      </Modal>
    </Page>
  );
}

function AppCard({
  module,
  dependencias,
  busy,
  onInstalar,
  onDesinstalar,
}: {
  module: Module;
  /** As que ainda não estão lá e virão junto. Quem instala precisa saber o que vem. */
  dependencias: Module[];
  busy: boolean;
  onInstalar: () => void;
  onDesinstalar: () => void;
}) {
  return (
    <Card className="flex flex-1 animate-rise flex-col">
      <div className="flex flex-1 flex-col p-6">
        <div className="flex items-start gap-4">
          <span
            aria-hidden="true"
            className="flex size-12 shrink-0 items-center justify-center rounded-dk bg-brand-soft text-xl text-brand-link"
          >
            {module.icon}
          </span>

          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-semibold leading-snug tracking-tight text-ink">
              {module.label}
            </h3>
            <p className="mt-0.5 text-xs tabular-nums text-ink-faint">v{module.version}</p>
          </div>

          {module.active && (
            <span className="shrink-0">
              <Badge tone="success" icon="✓">
                Instalado
              </Badge>
            </span>
          )}
        </div>

        <p className="mt-4 flex-1 text-base leading-relaxed text-ink-muted">
          {module.summary}
        </p>

        {dependencias.length > 0 && !module.active && (
          <p className="mt-3 text-sm text-ink-faint">
            Instala junto: {dependencias.map((item) => item.label).join(", ")}.
          </p>
        )}

        <div className="mt-6">
          {module.required ? (
            <p className="text-sm text-ink-faint">
              Faz parte da plataforma. Não pode ser desinstalado.
            </p>
          ) : module.active ? (
            <Button variant="secondary" inline loading={busy} onClick={onDesinstalar}>
              Desinstalar
            </Button>
          ) : (
            <Button inline loading={busy} onClick={onInstalar}>
              {busy ? "Instalando…" : "Instalar"}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
