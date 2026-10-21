import { useEffect, useState } from "react";

import { Button } from "../components/Button";
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
    <div className="mx-auto w-full max-w-2xl px-6 py-10">
      <h1 className="text-3xl font-bold text-ink">Qual é o ramo da sua empresa?</h1>
      <p className="mt-2 text-lg text-ink-muted">
        Escolha e o sistema já fica pronto para ele. Dá para mudar depois.
      </p>

      {error && (
        <p
          role="alert"
          className="mt-6 flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger"
        >
          <span aria-hidden="true" className="font-bold">
            !
          </span>
          {error}
        </p>
      )}

      {profiles === null && <p className="mt-6 text-lg text-ink-muted">Carregando…</p>}

      {profiles !== null && profiles.length === 0 && !error && (
        <p className="mt-6 rounded-dk border border-line bg-surface px-5 py-6 text-lg text-ink-muted">
          Nenhum ramo disponível nesta instalação ainda.
        </p>
      )}

      <ul className="mt-8 flex flex-col gap-4">
        {(profiles ?? []).map((profile) => (
          <li
            key={profile.name}
            className="rounded-dk border border-line bg-surface p-5"
          >
            <p className="text-2xl font-semibold text-ink">{profile.label}</p>
            <p className="mt-1 text-base text-ink-muted">{profile.description}</p>

            <div className="mt-4">
              {profile.active ? (
                <p className="rounded-dk bg-action-soft px-4 py-3 text-base text-ink">
                  Já contratado.
                </p>
              ) : (
                <Button onClick={() => contract(profile)} loading={busy === profile.name}>
                  {busy === profile.name ? "Preparando…" : "Usar este"}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
