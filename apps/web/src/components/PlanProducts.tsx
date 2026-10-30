import { useEffect, useState } from "react";

import { agro } from "../lib/agro";
import type { PlanProduct, Prescription, Product } from "../lib/agro";
import { dateBr, num, todayLocal } from "../lib/format";
import { Button } from "./Button";
import { Select } from "./Select";
import { TextField } from "./TextField";

interface Props {
  planId: string;
  prescriptionId: string | null;
}

/* A tabela de produtos e o receituário do planejamento.
 *
 * Os dois ficam juntos porque no talão também ficam: o formulário remete as precauções de
 * uso ao receituário, então um produto aplicado sem receituário vinculado é um documento
 * incompleto, não dois cadastros independentes.
 *
 * O cadastro de produto aparece aqui, na hora de usá-lo, e não só numa tela de cadastros:
 * em campo o produto que falta é descoberto no momento de lançá-lo, e mandar o operador
 * sair da tela para cadastrar é o tipo de atrito que faz voltar para o papel. */
export function PlanProducts({ planId, prescriptionId }: Props) {
  const [lines, setLines] = useState<PlanProduct[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [linked, setLinked] = useState<string | null>(prescriptionId);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([
      agro.listPlanProducts(planId),
      agro.listProducts(),
      agro.listPrescriptions(),
    ])
      .then(([planLines, registry, receituarios]) => {
        setLines(planLines);
        setProducts(registry);
        setPrescriptions(receituarios);
      })
      .catch(() => setError("Não foi possível carregar os produtos deste planejamento."));
  }, [planId]);

  const byId = new Map(products.map((product) => [product.id, product]));

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="mt-6 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle p-5">
        <h2 className="text-lg font-semibold text-ink">Produtos aplicados ({lines.length})</h2>
        <p className="mt-1 text-base text-ink-muted">
          As linhas saem impressas no relatório. Formulação e classe toxicológica são
          copiadas do cadastro no momento do lançamento.
        </p>

        {lines.length > 0 && (
          <ul className="mt-4 flex flex-col gap-3">
            {lines.map((line) => (
              <li
                key={line.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3 last:border-0"
              >
                <div>
                  <p className="text-base font-medium text-ink">
                    {byId.get(line.product_id)?.nome_comercial ?? "Produto"}
                  </p>
                  <p className="text-base text-ink-muted">
                    {[line.formulacao, line.classe_toxicologica && `classe ${line.classe_toxicologica}`]
                      .filter(Boolean)
                      .join(" · ") || "Sem formulação registrada"}
                  </p>
                  <p className="text-base text-ink-muted">
                    {num(line.dosagem_ha, 2)} /ha · calda {num(line.volume_ha, 2)} L/ha · total{" "}
                    {num(line.total_produto, 2)}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await agro.removePlanProduct(planId, line.id);
                      setLines(await agro.listPlanProducts(planId));
                    })
                  }
                  className="min-h-touch rounded-dk px-3 text-base font-medium text-danger hover:bg-danger-soft"
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}

        <AddProductLine
          products={products}
          busy={busy}
          onRegister={(body) =>
            run(async () => {
              const created = await agro.createProduct(body);
              setProducts(await agro.listProducts());
              return created;
            })
          }
          onAdd={(body) =>
            run(async () => {
              await agro.addPlanProduct(planId, body);
              setLines(await agro.listPlanProducts(planId));
            })
          }
        />

        {error && (
          <p
            role="alert"
            className="mt-5 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger"
          >
            {error}
          </p>
        )}
      </section>

      <section className="mt-6 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle p-5">
        <h2 className="text-lg font-semibold text-ink">Receituário agronômico</h2>
        <p className="mt-1 text-base text-ink-muted">
          O formulário remete as precauções de uso ao receituário. Sem o vínculo, o
          relatório sai sem a referência que a fiscalização procura.
        </p>

        <div className="mt-4 flex flex-col gap-4">
          <Select
            label="Receituário vinculado"
            value={linked ?? ""}
            onChange={(value) =>
              void run(async () => {
                const plan = await agro.linkPrescription(planId, value || null);
                setLinked(plan.prescription_id);
              })
            }
            disabled={busy}
            placeholder="Nenhum"
            options={prescriptions.map((item) => ({
              value: item.id,
              label: `${item.numero} · ${dateBr(item.emitido_em)}`,
            }))}
          />

          <NewPrescription
            busy={busy}
            onCreate={(body) =>
              run(async () => {
                const created = await agro.createPrescription(body);
                setPrescriptions(await agro.listPrescriptions());
                const plan = await agro.linkPrescription(planId, created.id);
                setLinked(plan.prescription_id);
              })
            }
          />
        </div>
      </section>
    </>
  );
}

interface AddProductLineProps {
  products: Product[];
  busy: boolean;
  onRegister: (body: {
    nome_comercial: string;
    formulacao: string | null;
    classe_toxicologica: string | null;
  }) => Promise<unknown>;
  onAdd: (body: {
    product_id: string;
    dosagem_ha: number | null;
    volume_ha: number | null;
    total_produto: number | null;
    adjuvante: string | null;
  }) => Promise<unknown>;
}

function AddProductLine({ products, busy, onRegister, onAdd }: AddProductLineProps) {
  const [open, setOpen] = useState(false);
  const [productId, setProductId] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [volume, setVolume] = useState("");
  const [total, setTotal] = useState("");
  const [adjuvante, setAdjuvante] = useState("");

  const [registering, setRegistering] = useState(false);
  const [nome, setNome] = useState("");
  const [formulacao, setFormulacao] = useState("");
  const [classe, setClasse] = useState("");

  if (!open) {
    return (
      <div className="mt-5">
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Lançar produto
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-5 flex flex-col gap-4 border-t border-line pt-5">
      <Select
        label="Produto"
        value={productId}
        onChange={setProductId}
        disabled={busy}
        placeholder="Selecione"
        options={products.map((product) => ({
          value: product.id,
          label: product.nome_comercial,
        }))}
      />

      {registering ? (
        <div className="flex flex-col gap-4 rounded-dk bg-brand-soft/40 p-4">
          <TextField
            label="Nome comercial"
            value={nome}
            onChange={(event) => setNome(event.target.value)}
          />
          <TextField
            label="Formulação"
            hint="Como vem no rótulo: SL, EC, WG…"
            value={formulacao}
            onChange={(event) => setFormulacao(event.target.value)}
          />
          <TextField
            label="Classe toxicológica"
            value={classe}
            onChange={(event) => setClasse(event.target.value)}
          />
          <Button
            disabled={nome.trim() === ""}
            loading={busy}
            onClick={() => {
              void onRegister({
                nome_comercial: nome.trim(),
                formulacao: formulacao.trim() || null,
                classe_toxicologica: classe.trim() || null,
              }).then(() => {
                setRegistering(false);
                setNome("");
                setFormulacao("");
                setClasse("");
              });
            }}
          >
            Cadastrar produto
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setRegistering(true)}
          className="min-h-touch self-start rounded-dk px-1 text-base font-medium text-brand-link"
        >
          O produto não está na lista
        </button>
      )}

      <TextField
        label="Dosagem por hectare"
        type="number"
        inputMode="decimal"
        step="any"
        value={dosagem}
        onChange={(event) => setDosagem(event.target.value)}
      />
      <TextField
        label="Volume de calda por hectare (L)"
        type="number"
        inputMode="decimal"
        step="any"
        value={volume}
        onChange={(event) => setVolume(event.target.value)}
      />
      {/* Não é calculado a partir de dosagem × área: o talão traz a coluna e quem a
          preenche é o receituário. Ver questão Q9 do discovery. */}
      <TextField
        label="Total do produto"
        hint="Como consta no receituário."
        type="number"
        inputMode="decimal"
        step="any"
        value={total}
        onChange={(event) => setTotal(event.target.value)}
      />
      <TextField
        label="Adjuvante"
        value={adjuvante}
        onChange={(event) => setAdjuvante(event.target.value)}
      />

      <div className="flex flex-col gap-3 sm:flex-row-reverse">
        <Button
          disabled={productId === ""}
          loading={busy}
          onClick={() => {
            void onAdd({
              product_id: productId,
              dosagem_ha: decimal(dosagem),
              volume_ha: decimal(volume),
              total_produto: decimal(total),
              adjuvante: adjuvante.trim() || null,
            }).then(() => {
              setProductId("");
              setDosagem("");
              setVolume("");
              setTotal("");
              setAdjuvante("");
              setOpen(false);
            });
          }}
        >
          Lançar no planejamento
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

interface NewPrescriptionProps {
  busy: boolean;
  onCreate: (body: {
    numero: string;
    emitido_em: string;
    agronomo_nome: string | null;
    agronomo_crea: string | null;
  }) => Promise<unknown>;
}

function NewPrescription({ busy, onCreate }: NewPrescriptionProps) {
  const [open, setOpen] = useState(false);
  const [numero, setNumero] = useState("");
  const [emitidoEm, setEmitidoEm] = useState(todayLocal);
  const [nome, setNome] = useState("");
  const [crea, setCrea] = useState("");

  if (!open) {
    return (
      <div>
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Cadastrar receituário
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 border-t border-line pt-5">
      <TextField
        label="Número"
        value={numero}
        onChange={(event) => setNumero(event.target.value)}
      />
      <TextField
        label="Emitido em"
        type="date"
        value={emitidoEm}
        onChange={(event) => setEmitidoEm(event.target.value)}
      />
      <TextField
        label="Engenheiro agrônomo"
        value={nome}
        onChange={(event) => setNome(event.target.value)}
      />
      <TextField
        label="CREA"
        value={crea}
        onChange={(event) => setCrea(event.target.value)}
      />

      <div className="flex flex-col gap-3 sm:flex-row-reverse">
        <Button
          disabled={numero.trim() === ""}
          loading={busy}
          onClick={() => {
            void onCreate({
              numero: numero.trim(),
              emitido_em: emitidoEm,
              agronomo_nome: nome.trim() || null,
              agronomo_crea: crea.trim() || null,
            }).then(() => {
              setOpen(false);
              setNumero("");
              setNome("");
              setCrea("");
            });
          }}
        >
          Cadastrar e vincular
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

/** Campo numérico vazio é ausência de informação, não zero. */
function decimal(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}
