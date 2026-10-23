import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader, Row } from "../components/Card";
import { Select } from "../components/Select";
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
    <Page wide>
      <PageHeader
        title="Unidades e embalagens"
        description="Comece pela unidade em que você conta o produto — peça, quilo, litro. Depois descreva as embalagens em cima dela: a caixa tem tantas peças, o fardo tem tantas caixas."
        onBack={onBack}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="h-fit">
          <CardHeader title="Nova unidade" />
          <CardBody>
            <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium text-ink">O que você vai criar</span>
                <div className="flex gap-1 rounded-dk bg-sunken p-1">
                  <button
                    type="button"
                    onClick={() => setReferenciaId("")}
                    aria-pressed={!criandoEmbalagem}
                    className={
                      "min-h-[2.5rem] flex-1 rounded-sm text-base font-medium " +
                      "transition-[background-color,box-shadow,color] duration-150 ease-dk " +
                      (!criandoEmbalagem
                        ? "bg-surface text-ink shadow-xs"
                        : "text-ink-muted hover:text-ink")
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
                      "min-h-[2.5rem] flex-1 rounded-sm text-base font-medium " +
                      "transition-[background-color,box-shadow,color] duration-150 ease-dk " +
                      "disabled:cursor-not-allowed disabled:text-ink-faint/60 " +
                      (criandoEmbalagem
                        ? "bg-surface text-ink shadow-xs"
                        : "text-ink-muted hover:text-ink")
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
                  <Select
                    label="Contém o quê"
                    hint="O fardo é descrito em caixas, não em peças — o sistema faz a conta."
                    value={referenciaId}
                    onChange={setReferenciaId}
                    options={(unidades ?? []).map((unidade) => ({
                      value: unidade.id,
                      label: unidade.nome,
                    }))}
                  />

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

              {error && <Alert tone="danger">{error}</Alert>}

              <Button
                type="submit"
                loading={busy}
                disabled={!nome || (criandoEmbalagem && !fator)}
              >
                Salvar
              </Button>
            </form>
          </CardBody>
        </Card>

        <Card className="h-fit">
          <CardHeader title={`Cadastradas (${unidades?.length ?? 0})`} />

          {unidades !== null && unidades.length === 0 ? (
            <CardBody>
              <p className="text-base text-ink-muted">Nenhuma ainda.</p>
            </CardBody>
          ) : (
            <ul className="mt-2 border-t border-line-subtle">
              {(unidades ?? []).map((unidade) => {
                const referencia = unidade.referencia_id
                  ? porId.get(unidade.referencia_id)
                  : undefined;
                return (
                  <Row key={unidade.id}>
                    <div className="min-w-0">
                      <p className="font-medium text-ink">
                        {unidade.nome}
                        {unidade.simbolo ? (
                          <span className="font-normal text-ink-muted">
                            {" "}
                            ({unidade.simbolo})
                          </span>
                        ) : null}
                      </p>
                      <p className="text-sm text-ink-muted">
                        {referencia
                          ? `${num(unidade.fator_relativo)} ${referencia.nome}`
                          : "Unidade de contagem"}
                      </p>
                    </div>
                    {referencia ? (
                      <Badge tone="info">
                        <span className="tabular">= {num(unidade.fator)}</span> na base
                      </Badge>
                    ) : (
                      <Badge tone="neutral">base</Badge>
                    )}
                  </Row>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </Page>
  );
}
