import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { comercial, describeUnidade } from "../lib/comercial";
import type { Lote, Movimento, Produto, Saldo, TipoMovimento, Unidade } from "../lib/comercial";
import { dateBr, num, todayLocal } from "../lib/format";

interface Props {
  produto: Produto;
  onBack: () => void;
}

const TIPOS: { value: TipoMovimento; label: string }[] = [
  { value: "entrada", label: "Entrada" },
  { value: "saida", label: "Saída" },
  { value: "ajuste", label: "Ajuste" },
];

export function ProdutoDetailPage({ produto, onBack }: Props) {
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [lotes, setLotes] = useState<Lote[]>([]);
  const [saldo, setSaldo] = useState<Saldo | null>(null);
  const [movimentos, setMovimentos] = useState<Movimento[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [tipo, setTipo] = useState<TipoMovimento>("entrada");
  const [quantidade, setQuantidade] = useState("");
  const [unidadeId, setUnidadeId] = useState(produto.unidade_id);
  const [loteId, setLoteId] = useState("");
  const [documento, setDocumento] = useState("");

  const [novoLote, setNovoLote] = useState("");
  const [novaValidade, setNovaValidade] = useState("");

  async function load() {
    const [u, l, s, m] = await Promise.all([
      comercial.listUnidades(),
      comercial.listLotes(produto.id),
      comercial.saldo(produto.id),
      comercial.movimentos(produto.id),
    ]);
    setUnidades(u);
    setLotes(l);
    setSaldo(s);
    setMovimentos(m);
  }

  useEffect(() => {
    load().catch((cause) =>
      setError(cause instanceof Error ? cause.message : String(cause)),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [produto.id]);

  const porId = new Map(unidades.map((u) => [u.id, u]));
  const raiz = unidades.find((u) => u.referencia_id === null);
  const base = porId.get(produto.unidade_id);
  const escolhida = porId.get(unidadeId);

  // Converter antes de salvar: o lojista confere o que vai entrar, em vez de descobrir
  // depois que digitou fardo onde queria caixa.
  const convertido =
    quantidade && escolhida && base
      ? (Number(quantidade) * Number(escolhida.fator)) / Number(base.fator)
      : null;

  async function criarLote(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const lote = await comercial.createLote({
        produto_id: produto.id,
        codigo: novoLote.trim(),
        validade: novaValidade || null,
      });
      setNovoLote("");
      setNovaValidade("");
      await load();
      setLoteId(lote.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar o lote.");
    } finally {
      setBusy(false);
    }
  }

  async function movimentar(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await comercial.movimentar({
        produto_id: produto.id,
        tipo,
        quantidade: Number(quantidade),
        unidade_id: unidadeId,
        lote_id: loteId || null,
        documento: documento.trim() || null,
      });
      setQuantidade("");
      setDocumento("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível registrar.");
    } finally {
      setBusy(false);
    }
  }

  const hoje = todayLocal();

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <button
        type="button"
        onClick={onBack}
        className="min-h-touch text-base font-medium text-brand-link"
      >
        ← Voltar
      </button>

      <h1 className="mt-2 text-3xl font-bold text-ink">{produto.nome}</h1>
      <p className="mt-1 text-lg text-ink-muted">
        {produto.codigo}
        {produto.gtin ? ` · ${produto.gtin}` : ""}
      </p>

      <section className="mt-8 rounded-dk border border-line bg-surface p-5">
        <h2 className="text-xl font-semibold text-ink">Em estoque</h2>
        <p className="mt-1 text-4xl font-bold text-ink">
          {num(saldo?.quantidade ?? 0, 3)}{" "}
          <span className="text-xl font-medium text-ink-muted">
            {base?.simbolo ?? base?.nome ?? ""}
          </span>
        </p>

        {produto.controla_lote && (saldo?.por_lote.length ?? 0) > 0 && (
          <ul className="mt-5 flex flex-col gap-3">
            {saldo?.por_lote.map((item) => {
              const vencido = item.validade !== null && item.validade < hoje;
              return (
                <li
                  key={item.lote_id ?? "sem-lote"}
                  className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3 last:border-0"
                >
                  <div>
                    <p className="text-base font-medium text-ink">
                      {item.codigo ?? "Sem lote"}
                    </p>
                    {item.validade && (
                      <p className="text-base text-ink-muted">
                        Validade {dateBr(item.validade)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Vencido não é só cor: vem ícone e palavra. */}
                    {vencido && (
                      <span className="rounded-dk bg-warn-soft px-3 py-1 text-sm font-medium text-ink">
                        ⚠ Vencido
                      </span>
                    )}
                    <p className="text-lg font-semibold text-ink">
                      {num(item.quantidade, 3)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="mt-6 rounded-dk border border-line bg-surface p-5">
        <h2 className="text-xl font-semibold text-ink">Movimentar estoque</h2>

        <form onSubmit={movimentar} className="mt-5 flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <span className="text-base font-medium text-ink">O que aconteceu</span>
            <div className="flex gap-2">
              {TIPOS.map((opcao) => (
                <button
                  key={opcao.value}
                  type="button"
                  onClick={() => setTipo(opcao.value)}
                  aria-pressed={tipo === opcao.value}
                  className={
                    "min-h-touch flex-1 rounded-dk border text-lg font-medium " +
                    (tipo === opcao.value
                      ? "border-action bg-action-soft text-ink"
                      : "border-line bg-surface text-ink-muted")
                  }
                >
                  {opcao.label}
                </button>
              ))}
            </div>
          </div>

          <TextField
            label="Quantidade"
            type="number"
            inputMode="decimal"
            value={quantidade}
            onChange={(e) => setQuantidade(e.target.value)}
            required
          />

          <div className="flex flex-col gap-1.5">
            <label className="text-base font-medium text-ink">Em que embalagem</label>
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
            {convertido !== null && unidadeId !== produto.unidade_id && (
              <p className="rounded-dk bg-brand-soft px-4 py-2 text-base text-ink">
                Vai entrar como <b>{num(convertido, 3)}</b>{" "}
                {base?.simbolo ?? base?.nome ?? ""} no saldo.
              </p>
            )}
          </div>

          {produto.controla_lote && (
            <div className="flex flex-col gap-1.5">
              <label className="text-base font-medium text-ink">Lote</label>
              <select
                value={loteId}
                onChange={(e) => setLoteId(e.target.value)}
                className="min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink"
              >
                <option value="">Selecione…</option>
                {lotes.map((lote) => (
                  <option key={lote.id} value={lote.id}>
                    {lote.codigo}
                    {lote.validade ? ` — vence ${dateBr(lote.validade)}` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <TextField
            label="Documento"
            hint="Número da nota, cupom ou contagem. Opcional."
            value={documento}
            onChange={(e) => setDocumento(e.target.value)}
          />

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

          <Button
            type="submit"
            loading={busy}
            disabled={!quantidade || (produto.controla_lote && !loteId)}
          >
            Registrar
          </Button>
        </form>
      </section>

      {produto.controla_lote && (
        <section className="mt-6 rounded-dk border border-line bg-surface p-5">
          <h2 className="text-xl font-semibold text-ink">Novo lote</h2>
          <form onSubmit={criarLote} className="mt-4 flex flex-col gap-4" noValidate>
            <TextField
              label="Código do lote"
              value={novoLote}
              onChange={(e) => setNovoLote(e.target.value)}
            />
            {produto.controla_validade && (
              <TextField
                label="Validade"
                type="date"
                value={novaValidade}
                onChange={(e) => setNovaValidade(e.target.value)}
              />
            )}
            <Button variant="ghost" type="submit" disabled={!novoLote.trim()}>
              Cadastrar lote
            </Button>
          </form>
        </section>
      )}

      <section className="mt-6 rounded-dk border border-line bg-surface p-5">
        <h2 className="text-xl font-semibold text-ink">
          Histórico ({movimentos.length})
        </h2>
        <p className="mt-1 text-base text-ink-muted">
          É daqui que sai o saldo. Nada é apagado: correção entra como ajuste.
        </p>

        {movimentos.length === 0 ? (
          <p className="mt-4 text-base text-ink-muted">Nenhuma movimentação ainda.</p>
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {[...movimentos].reverse().map((movimento) => (
              <li
                key={movimento.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3 last:border-0"
              >
                <div>
                  <p className="text-base font-medium text-ink">
                    {TIPOS.find((t) => t.value === movimento.tipo)?.label}
                    {movimento.documento ? ` · ${movimento.documento}` : ""}
                  </p>
                  <p className="text-base text-ink-muted">
                    {dateBr(movimento.ocorrido_em.slice(0, 10))} ·{" "}
                    {num(movimento.quantidade_digitada, 3)}{" "}
                    {porId.get(movimento.unidade_id)?.nome ?? ""}
                  </p>
                </div>
                <p className="text-lg font-semibold text-ink">
                  {movimento.tipo === "saida" ? "−" : "+"}
                  {num(movimento.quantidade, 3)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
