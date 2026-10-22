import { useEffect, useState } from "react";

import { TextField } from "../components/TextField";
import { Wizard } from "../components/Wizard";
import { comercial, describeUnidade } from "../lib/comercial";
import type { Categoria, Produto, Unidade } from "../lib/comercial";

const STEPS = ["O que é o produto", "Como você conta", "Preço e controle"];

interface Props {
  onCancel: () => void;
  onCreated: (produto: Produto) => void;
}

export function NovoProdutoWizard({ onCancel, onCreated }: Props) {
  const [step, setStep] = useState(0);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [codigo, setCodigo] = useState("");
  const [nome, setNome] = useState("");
  const [gtin, setGtin] = useState("");
  const [unidadeId, setUnidadeId] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  const [precoCusto, setPrecoCusto] = useState("");
  const [precoVenda, setPrecoVenda] = useState("");
  const [controlaLote, setControlaLote] = useState(false);
  const [controlaValidade, setControlaValidade] = useState(false);

  useEffect(() => {
    Promise.all([comercial.listUnidades(), comercial.listCategorias()])
      .then(([u, c]) => {
        setUnidades(u);
        setCategorias(c);
        // A unidade de contagem é a escolha certa em quase todo caso: o saldo soma nela.
        setUnidadeId(u.find((item) => item.referencia_id === null)?.id ?? u[0]?.id ?? "");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, []);

  const raiz = unidades.find((u) => u.referencia_id === null);

  function back() {
    setError(null);
    if (step === 0) onCancel();
    else setStep((value) => value - 1);
  }

  async function next() {
    setError(null);
    if (step < STEPS.length - 1) {
      setStep((value) => value + 1);
      return;
    }

    setBusy(true);
    try {
      onCreated(
        await comercial.createProduto({
          codigo: codigo.trim(),
          nome: nome.trim(),
          gtin: gtin.trim() || null,
          unidade_id: unidadeId,
          categoria_id: categoriaId || null,
          preco_custo: precoCusto ? Number(precoCusto) : null,
          preco_venda: precoVenda ? Number(precoVenda) : null,
          controla_lote: controlaLote,
          // Controlar validade sem controlar lote não se sustenta: a validade pertence
          // ao lote, não ao produto.
          controla_validade: controlaValidade && controlaLote,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar.");
    } finally {
      setBusy(false);
    }
  }

  const bloqueado =
    (step === 0 && (!codigo.trim() || !nome.trim())) || (step === 1 && !unidadeId);

  return (
    <div className="mx-auto w-full max-w-xl px-6 py-8">
      <Wizard
        steps={STEPS}
        current={step}
        onBack={back}
        onNext={next}
        nextLabel="Cadastrar produto"
        nextDisabled={bloqueado}
        busy={busy}
      >
        {step === 0 && (
          <>
            <TextField
              label="Nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              required
            />
            <TextField
              label="Código interno"
              hint="Como você chama esse item na sua loja."
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              required
            />
            <TextField
              label="Código de barras"
              hint="Opcional. Só números."
              inputMode="numeric"
              value={gtin}
              onChange={(e) => setGtin(e.target.value.replace(/\D/g, ""))}
            />
          </>
        )}

        {step === 1 && (
          <>
            <div className="flex flex-col gap-1.5">
              <label className="text-base font-medium text-ink">Unidade de contagem</label>
              <select
                value={unidadeId}
                onChange={(e) => setUnidadeId(e.target.value)}
                className="min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink"
              >
                {unidades.map((unidade) => (
                  <option key={unidade.id} value={unidade.id}>
                    {describeUnidade(unidade, raiz)}
                  </option>
                ))}
              </select>
              <p className="text-sm text-ink-muted">
                É nela que o saldo é somado. Você ainda poderá dar entrada em caixa ou
                fardo — o sistema converte.
              </p>
            </div>

            {categorias.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <label className="text-base font-medium text-ink">Categoria</label>
                <select
                  value={categoriaId}
                  onChange={(e) => setCategoriaId(e.target.value)}
                  className="min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink"
                >
                  <option value="">Sem categoria</option>
                  {categorias.map((categoria) => (
                    <option key={categoria.id} value={categoria.id}>
                      {categoria.nome}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </>
        )}

        {step === 2 && (
          <>
            <TextField
              label="Preço de venda"
              type="number"
              inputMode="decimal"
              value={precoVenda}
              onChange={(e) => setPrecoVenda(e.target.value)}
            />
            <TextField
              label="Preço de custo"
              hint="Opcional."
              type="number"
              inputMode="decimal"
              value={precoCusto}
              onChange={(e) => setPrecoCusto(e.target.value)}
            />

            <Toggle
              label="Controlar lote"
              hint="Para saber de qual remessa é cada item. Obrigatório para controlar validade."
              checked={controlaLote}
              onChange={(value) => {
                setControlaLote(value);
                if (!value) setControlaValidade(false);
              }}
            />
            <Toggle
              label="Controlar validade"
              hint={
                controlaLote
                  ? "A validade fica no lote."
                  : "Ative o controle de lote primeiro: a validade pertence ao lote."
              }
              checked={controlaValidade}
              disabled={!controlaLote}
              onChange={setControlaValidade}
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
      </Wizard>
    </div>
  );
}

interface ToggleProps {
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}

function Toggle({ label, hint, checked, disabled = false, onChange }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={
        "flex min-h-touch w-full items-start gap-3 rounded-dk border px-4 py-3 text-left " +
        "disabled:cursor-not-allowed disabled:opacity-60 " +
        (checked ? "border-action bg-action-soft" : "border-line bg-surface")
      }
    >
      {/* Não é só cor: o estado vem escrito, e o botão carrega role e aria-checked. */}
      <span aria-hidden="true" className="mt-0.5 text-xl font-bold text-ink">
        {checked ? "☑" : "☐"}
      </span>
      <span>
        <span className="block text-lg font-medium text-ink">{label}</span>
        <span className="block text-base text-ink-muted">{hint}</span>
      </span>
    </button>
  );
}
