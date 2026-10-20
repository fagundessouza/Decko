import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { ThemeToggle } from "../components/ThemeToggle";
import { login } from "../lib/api";
import type { SessionInfo } from "../lib/api";
import { session } from "../lib/session";

interface Props {
  onSignedIn: (info: SessionInfo) => void;
}

export function LoginPage({ onSignedIn }: Props) {
  const [tenantSlug, setTenantSlug] = useState(session.getTenantSlug());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      onSignedIn(await login({ tenantSlug, email, password }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível entrar.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-bg lg:flex-row">
      {/* Faixa de marca. Azul-grafite é estrutura, nunca ação. */}
      <aside
        className="flex shrink-0 flex-col justify-between bg-brand px-6 py-6
                   text-white lg:w-2/5 lg:px-12 lg:py-12"
      >
        <p className="text-3xl font-bold tracking-tight">Decko</p>
        <p className="mt-6 hidden max-w-sm text-xl leading-relaxed text-white/80 lg:block">
          Gestão que acompanha o ritmo do seu negócio, sem travar o caixa e sem papel.
        </p>
        <p className="mt-6 hidden text-base text-white/60 lg:block">
          Seus dados ficam isolados dos de qualquer outra empresa.
        </p>
      </aside>

      <main className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="w-full max-w-md">
          <h1 className="text-3xl font-bold text-ink">Entrar</h1>
          <p className="mt-2 text-lg text-ink-muted">Informe seus dados de acesso.</p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5" noValidate>
            <TextField
              label="Código da empresa"
              hint="O mesmo código todo dia. Fica guardado neste aparelho."
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value)}
              autoComplete="organization"
              autoCapitalize="none"
              spellCheck={false}
              required
            />

            <TextField
              label="E-mail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
            />

            <TextField
              label="Senha"
              revealable
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />

            {/* O erro traz ícone e texto além da cor: daltonismo e tela de PDV desbotada
                são realidade no público-alvo. */}
            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3
                           text-base text-danger"
              >
                <span aria-hidden="true" className="font-bold">
                  !
                </span>
                {error}
              </p>
            )}

            <Button type="submit" loading={busy}>
              {busy ? "Entrando…" : "Entrar"}
            </Button>
          </form>

          <div className="mt-8 flex justify-center">
            <ThemeToggle />
          </div>
        </div>
      </main>
    </div>
  );
}
