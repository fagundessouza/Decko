import { useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "../components/Alert";
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
      {/* Faixa de marca. Azul-grafite é estrutura, nunca ação.
          O brilho ao fundo dá profundidade sem imagem: nada para carregar, e continua
          legível em tela fraca. */}
      <aside className="relative isolate flex shrink-0 flex-col justify-between overflow-hidden bg-brand-deep px-6 py-7 text-white lg:w-[42%] lg:px-14 lg:py-14">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-32 -z-10 size-96 rounded-full bg-brand-link/25 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-40 -right-24 -z-10 size-96 rounded-full bg-action/15 blur-3xl"
        />

        <p className="text-2xl font-bold tracking-tight lg:text-3xl">Decko</p>

        <div className="hidden lg:block">
          <p className="max-w-sm text-2xl font-medium leading-snug tracking-tight text-white">
            Gestão que acompanha o ritmo do seu negócio, sem travar o caixa e sem papel.
          </p>
          <ul className="mt-8 flex flex-col gap-3 text-base text-white/70">
            {[
              "Seus dados isolados dos de qualquer outra empresa",
              "Funciona no computador do caixa e no celular",
              "Você escolhe o ramo e o sistema fica pronto",
            ].map((item) => (
              <li key={item} className="flex items-start gap-3">
                <span aria-hidden="true" className="mt-0.5 text-action-bright">
                  ✓
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-6 hidden text-sm text-white/40 lg:block">
          Decko · plataforma de gestão
        </p>
      </aside>

      <main className="flex flex-1 items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-sm animate-rise">
          <h1 className="text-3xl font-bold tracking-tight text-ink">Entrar</h1>
          <p className="mt-2 text-base text-ink-muted">Informe seus dados de acesso.</p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4" noValidate>
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

            {error && <Alert tone="danger">{error}</Alert>}

            <div className="mt-2">
              <Button type="submit" size="lg" loading={busy}>
                {busy ? "Entrando…" : "Entrar"}
              </Button>
            </div>
          </form>

          <div className="mt-8 flex justify-center">
            <ThemeToggle />
          </div>
        </div>
      </main>
    </div>
  );
}
