import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Page, PageHeader } from "../components/AppShell";
import { Alert } from "../components/Alert";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader, Row } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
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

  const [loteModal, setLoteModal] = useState(false);
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
      setLoteModal(false);
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
    <Page wide>
      <PageHeader
        title={produto.nome}
        description={`${produto.codigo}${produto.gtin ? ` · ${produto.gtin}` : ""}`}
        onBack={onBack}
      />

      {/* O saldo é o número que o lojista vem buscar: ganha destaque de verdade,
          não mais uma linha igual às outras. */}
      <Card className="mb-6 overflow-hidden">
        <div className="flex flex-wrap items-end justify-between gap-6 bg-gradient-to-br from-brand-tint to-surface p-6 sm:p-8">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-ink-muted">
              Em estoque
            </p>
            <p className="tabular mt-2 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
              {num(saldo?.quantidade ?? 0, 3)}
              <span className="ml-2 text-xl font-medium text-ink-muted">
                {base?.simbolo ?? base?.nome ?? ""}
              </span>
            </p>
          </div>
          {produto.preco_venda && (
            <div className="text-right">
              <p className="text-sm font-medium uppercase tracking-wide text-ink-muted">
                Preço de venda
              </p>
              <p className="tabular mt-2 text-2xl font-semibold text-ink">
                R$ {num(produto.preco_venda, 2)}
              </p>
            </div>
          )}
        </div>

        {produto.controla_lote && (saldo?.por_lote.length ?? 0) > 0 && (
          <ul className="border-t border-line-subtle">
            {saldo?.por_lote.map((item) => {
              const vencido = item.validade !== null && item.validade < hoje;
              return (
                <Row key={item.lote_id ?? "sem-lote"}>
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{item.codigo ?? "Sem lote"}</p>
                    {item.validade && (
                      <p className="text-sm text-ink-muted">
                        Validade {dateBr(item.validade)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Vencido não é só cor: vem ícone e palavra. */}
                    {vencido && (
                      <Badge tone="warn" icon="⚠">
                        Vencido
                      </Badge>
                    )}
                    <span className="tabular font-semibold text-ink">
                      {num(item.quantidade, 3)}
                    </span>
                  </div>
                </Row>
              );
            })}
          </ul>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="Movimentar estoque"
              description="A quantidade pode ser digitada em qualquer embalagem."
            />
            <CardBody>
              <form onSubmit={movimentar} className="flex flex-col gap-4" noValidate>
                <div className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium text-ink">O que aconteceu</span>
                  <div className="flex gap-1 rounded-dk bg-sunken p-1">
                    {TIPOS.map((opcao) => (
                      <button
                        key={opcao.value}
                        type="button"
                        onClick={() => setTipo(opcao.value)}
                        aria-pressed={tipo === opcao.value}
                        className={
                          "min-h-[2.5rem] flex-1 rounded-sm text-base font-medium " +
                          "transition-[background-color,box-shadow,color] duration-150 ease-dk " +
                          (tipo === opcao.value
                            ? "bg-surface text-ink shadow-xs"
                            : "text-ink-muted hover:text-ink")
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

                <Select
                  label="Em que embalagem"
                  value={unidadeId}
                  onChange={setUnidadeId}
                  options={unidades.map((unidade) => ({
                    value: unidade.id,
                    label: describeUnidade(unidade, raiz),
                  }))}
                />

                {convertido !== null && unidadeId !== produto.unidade_id && (
                  <p className="animate-fade rounded-dk bg-brand-soft px-4 py-3 text-base text-ink ring-1 ring-inset ring-brand-link/15">
                    Vai entrar como{" "}
                    <b className="tabular">{num(convertido, 3)}</b>{" "}
                    {base?.simbolo ?? base?.nome ?? ""} no saldo.
                  </p>
                )}

                {produto.controla_lote && (
                  <div className="flex flex-col gap-2">
                    <Select
                      label="Lote"
                      value={loteId}
                      onChange={setLoteId}
                      placeholder="Selecione…"
                      options={lotes.map((lote) => ({
                        value: lote.id,
                        label: `${lote.codigo}${lote.validade ? ` — vence ${dateBr(lote.validade)}` : ""}`,
                      }))}
                    />
                    {/* Cadastrar lote é tarefa curta e secundária: sai em sobreposição
                        para não empurrar o formulário principal tela abaixo. */}
                    <button
                      type="button"
                      onClick={() => setLoteModal(true)}
                      className="self-start text-sm font-medium text-brand-link hover:underline"
                    >
                      + Cadastrar novo lote
                    </button>
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
                    className="flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger ring-1 ring-inset ring-danger/20"
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
            </CardBody>
          </Card>

        </div>

        <Card>
          <CardHeader
            title={`Histórico (${movimentos.length})`}
            description="É daqui que sai o saldo. Nada é apagado: correção entra como ajuste."
          />

          {movimentos.length === 0 ? (
            <CardBody>
              <p className="text-base text-ink-muted">Nenhuma movimentação ainda.</p>
            </CardBody>
          ) : (
            <ul className="mt-2 border-t border-line-subtle">
              {[...movimentos].reverse().map((movimento) => (
                <Row key={movimento.id}>
                  <div className="min-w-0">
                    <p className="font-medium text-ink">
                      {TIPOS.find((t) => t.value === movimento.tipo)?.label}
                      {movimento.documento ? (
                        <span className="font-normal text-ink-muted">
                          {" "}
                          · {movimento.documento}
                        </span>
                      ) : null}
                    </p>
                    <p className="text-sm text-ink-muted">
                      {dateBr(movimento.ocorrido_em.slice(0, 10))} ·{" "}
                      <span className="tabular">
                        {num(movimento.quantidade_digitada, 3)}
                      </span>{" "}
                      {porId.get(movimento.unidade_id)?.nome ?? ""}
                    </p>
                  </div>
                  <span
                    className={
                      "tabular shrink-0 font-semibold " +
                      (movimento.tipo === "saida" ? "text-ink-muted" : "text-action")
                    }
                  >
                    {movimento.tipo === "saida" ? "−" : "+"}
                    {num(movimento.quantidade, 3)}
                  </span>
                </Row>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Modal
        open={loteModal}
        title="Novo lote"
        description={`Para ${produto.nome}.`}
        onClose={() => setLoteModal(false)}
      >
        <form id="form-lote" onSubmit={criarLote} className="flex flex-col gap-4" noValidate>
          <TextField
            label="Código do lote"
            hint="Como vem impresso na embalagem ou na nota."
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
          {error && <Alert tone="danger">{error}</Alert>}
        </form>

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button inline variant="secondary" onClick={() => setLoteModal(false)}>
            Cancelar
          </Button>
          <Button
            inline
            type="submit"
            form="form-lote"
            loading={busy}
            disabled={!novoLote.trim()}
          >
            Cadastrar lote
          </Button>
        </div>
      </Modal>
    </Page>
  );
}
