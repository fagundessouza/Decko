import { useEffect, useState } from "react";

import { Button } from "./components/Button";
import { ThemeToggle } from "./components/ThemeToggle";
import { logout, restoreSession } from "./lib/api";
import type { SessionInfo } from "./lib/api";
import { LoginPage } from "./pages/LoginPage";

export default function App() {
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);

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

  return (
    <div className="min-h-dvh bg-bg">
      <header className="flex items-center justify-between gap-4 bg-brand px-6 py-4 text-white">
        <div>
          <p className="text-xl font-bold tracking-tight">Decko</p>
          <p className="text-base text-white/70">{info.tenant.name}</p>
        </div>
        <p className="hidden text-base text-white/80 sm:block">{info.user.full_name}</p>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-3xl font-bold text-ink">Olá, {info.user.full_name}</h1>
        <p className="mt-2 text-lg text-ink-muted">
          Nenhum módulo de negócio instalado ainda nesta empresa.
        </p>

        <section className="mt-8 rounded-dk border border-line bg-surface p-6">
          <h2 className="text-xl font-semibold text-ink">Seus acessos</h2>
          <p className="mt-1 text-base text-ink-muted">
            {info.permissions.length} permissões concedidas.
          </p>
          <ul className="mt-4 flex flex-wrap gap-2">
            {info.permissions.map((permission) => (
              <li
                key={permission}
                className="rounded-dk bg-brand-soft px-3 py-1.5 text-sm text-ink"
              >
                {permission}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
          <ThemeToggle />
          <div className="w-full sm:w-auto">
            <Button
              variant="ghost"
              onClick={() => {
                void logout().then(() => setInfo(null));
              }}
            >
              Sair
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
