import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { comercial } from "../lib/comercial";
import type { Unidade } from "../lib/comercial";
import { num } from "../lib/format";

interface Props {
  onBack: () => void;
  onChanged?: () => void;
}

export function UnidadesPage({ onBack, onChanged }: Props) {
  const [unidades, setUnidades] = useState<Unidade[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [nome, setNome] = useState("");
  const [simbolo, setSimbolo] = useState("");
  const [referenciaId, setReferenciaId] = useState("");
  const [fator, setFator] = useState("");

  async function load() {
    try {
      setUnidades(await comercial.listUnidades());
    } catch (cause) {
      setUnidades([]);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const raizes = (unidades ?? []).filter((u) => u.referencia_id === null);
  const porId = new Map((unidades ?? []).map((u) => [u.id, u]));
  const criandoEmbalagem = referenciaId !== "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await comercial.createUnidade({
        nome,
        simbolo: simbolo || null,
        referencia_id: referenciaId || null,
        fator_relativo: criandoEmbalagem ? Number(fator) : 1,
      });
      setNome("");
      setSimbolo("");
      setFator("");
      await load();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <button
        type="button"
        onClick={onBack}
        className="min-h-touch text-base font-medium text-brand-link"
      >
        ← Voltar
      </button>

      <h1 className="mt-2 text-3xl font-bold text-ink">Unidades e embalagens</h1>
      <p className="mt-2 text-lg text-ink-muted">
        Comece pela unidade em que você conta o produto — peça, quilo, litro. Depois
        descreva as embalagens em cima dela: a caixa tem tantas peças, o fardo tem tantas
        caixas.
      </p>

      <section className="mt-8 rounded-dk border border-line bg-surface p-5">
        <h2 className="text-xl font-semibold text-ink">Nova unidade</h2>

        <form onSubmit={submit} className="mt-5 flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <label className="text-base font-medium text-ink">O que você vai criar</label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={() => setReferenciaId("")}
                aria-pressed={!criandoEmbalagem}
                className={
                  "min-h-touch flex-1 rounded-dk border px-4 text-lg font-medium " +
                  (!criandoEmbalagem
                    ? "border-action bg-action-soft text-ink"
                    : "border-line bg-surface text-ink-muted")
                }
              >
                Unidade de contagem
              </button>
              <button
                type="button"
                onClick={() => setReferenciaId(raizes[0]?.id ?? "")}
                disabled={raizes.length === 0}
                aria-pressed={criandoEmbalagem}
                className={
                  "min-h-touch flex-1 rounded-dk border px-4 text-lg font-medium " +
                  "disabled:cursor-not-allowed disabled:text-ink-muted/50 " +
                  (criandoEmbalagem
                    ? "border-action bg-action-soft text-ink"
                    : "border-line bg-surface text-ink-muted")
                }
              >
                Embalagem
              </button>
            </div>
            {raizes.length === 0 && (
              <p className="text-sm text-ink-muted">
                Crie primeiro uma unidade de contagem para poder descrever embalagens.
              </p>
            )}
          </div>

          <TextField
            label="Nome"
            hint={criandoEmbalagem ? "Caixa, fardo, pacote…" : "Peça, quilo, litro…"}
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
          />

          {!criandoEmbalagem && (
            <TextField
              label="Símbolo"
              hint="Opcional. Aparece nos documentos: un, kg, L."
              value={simbolo}
              onChange={(e) => setSimbolo(e.target.value)}
            />
          )}

          {criandoEmbalagem && (
            <>
              <div className="flex flex-col gap-1.5">
                <label className="text-base font-medium text-ink">Contém o quê</label>
                <select
                  value={referenciaId}
                  onChange={(e) => setReferenciaId(e.target.value)}
                  className="min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink"
                >
                  {(unidades ?? []).map((unidade) => (
                    <option key={unidade.id} value={unidade.id}>
                      {unidade.nome}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-ink-muted">
                  O fardo é descrito em caixas, não em peças — o sistema faz a conta.
                </p>
              </div>

              <TextField
                label="Quantas"
                type="number"
                inputMode="decimal"
                hint={`Quantas ${porId.get(referenciaId)?.nome ?? "unidades"} cabem nesta embalagem.`}
                value={fator}
                onChange={(e) => setFator(e.target.value)}
                required
              />
            </>
          )}

          {error && (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger"
            >
              <span aria-hidden="true" className="font-bold">
                !
              </span>
              {error}
            </p>
          )}

          <Button type="submit" loading={busy} disabled={!nome || (criandoEmbalagem && !fator)}>
            Salvar
          </Button>
        </form>
      </section>

      <section className="mt-6 rounded-dk border border-line bg-surface p-5">
        <h2 className="text-xl font-semibold text-ink">
          Cadastradas ({unidades?.length ?? 0})
        </h2>

        {unidades !== null && unidades.length === 0 && (
          <p className="mt-2 text-base text-ink-muted">Nenhuma ainda.</p>
        )}

        <ul className="mt-4 flex flex-col gap-3">
          {(unidades ?? []).map((unidade) => {
            const referencia = unidade.referencia_id
              ? porId.get(unidade.referencia_id)
              : undefined;
            return (
              <li key={unidade.id} className="border-b border-line pb-3 last:border-0">
                <p className="text-base font-medium text-ink">
                  {unidade.nome}
                  {unidade.simbolo ? ` (${unidade.simbolo})` : ""}
                </p>
                <p className="text-base text-ink-muted">
                  {referencia
                    ? `${num(unidade.fator_relativo)} ${referencia.nome} · equivale a ${num(unidade.fator)} na unidade de contagem`
                    : "Unidade de contagem"}
                </p>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
