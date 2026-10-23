import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { platform } from "../lib/profiles";
import type { Profile } from "../lib/profiles";

interface Props {
  /** Chamado depois de contratar, para a sessão ser relida com os módulos novos. */
  onContracted: () => void;
}

/* A primeira coisa que o dono da empresa vê quando ainda não há nada ativo. Ele escolhe o
 * ramo — que é o que ele sabe — e o sistema liga os módulos, que é o que ele não precisa
 * saber. Ver docs/adr/0005-perfil-de-segmento.md. */
export function ChooseProfilePage({ onContracted }: Props) {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    platform
      .listProfiles()
      .then(setProfiles)
      .catch((cause) => {
        setProfiles([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      });
  }, []);

  async function contract(profile: Profile) {
    setBusy(profile.name);
    setError(null);
    try {
      await platform.activateProfile(profile.name);
      onContracted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível contratar.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Page wide>
      <PageHeader
        title="Qual é o ramo da sua empresa?"
        description="Escolha e o sistema já fica pronto para ele. Dá para mudar depois."
      />

      {error && (
        <div className="mb-6">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}

      {profiles === null && (
        <p className="animate-fade text-base text-ink-muted">Carregando…</p>
      )}

      {profiles !== null && profiles.length === 0 && !error && (
        <Card muted>
          <p className="px-6 py-10 text-center text-base text-ink-muted">
            Nenhum ramo disponível nesta instalação ainda.
          </p>
        </Card>
      )}

      <ul className="grid gap-5 sm:grid-cols-2">
        {(profiles ?? []).map((profile) => (
          <li key={profile.name} className="flex">
            <Card className="flex flex-1 animate-rise flex-col">
              <div className="flex flex-1 flex-col p-6">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-xl font-semibold tracking-tight text-ink">
                    {profile.label}
                  </h2>
                  {profile.active && (
                    <Badge tone="success" icon="✓">
                      Contratado
                    </Badge>
                  )}
                </div>

                <p className="mt-3 flex-1 text-base leading-relaxed text-ink-muted">
                  {profile.description}
                </p>

                <div className="mt-6">
                  {profile.active ? (
                    <p className="text-sm text-ink-muted">
                      Já disponível no menu desta empresa.
                    </p>
                  ) : (
                    <Button
                      onClick={() => contract(profile)}
                      loading={busy === profile.name}
                    >
                      {busy === profile.name ? "Preparando…" : "Usar este"}
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </Page>
  );
}
