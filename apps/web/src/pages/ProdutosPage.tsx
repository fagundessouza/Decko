import { useEffect, useState } from "react";

import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, Row } from "../components/Card";
import { comercial } from "../lib/comercial";
import type { Produto, Unidade } from "../lib/comercial";
import { ncmMask, num } from "../lib/format";

interface Props {
  onBack: () => void;
  onOpen: (produto: Produto) => void;
  onNew: () => void;
  onUnidades: () => void;
  onConferencia: () => void;
}

export function ProdutosPage({ onBack, onOpen, onNew, onUnidades, onConferencia }: Props) {
  const [produtos, setProdutos] = useState<Produto[] | null>(null);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [busca, setBusca] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([comercial.listProdutos(), comercial.listUnidades()])
      .then(([p, u]) => {
        setProdutos(p);
        setUnidades(u);
      })
      .catch((cause) => {
        setProdutos([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      });
  }, []);

  const porId = new Map(unidades.map((u) => [u.id, u]));
  const termo = busca.trim().toLowerCase();
  // O NCM é guardado sem máscara, mas o comprador manda com ponto. Compara só dígitos.
  const digitos = termo.replace(/\D/g, "");
  const visiveis = (produtos ?? []).filter(
    (produto) =>
      !termo ||
      produto.nome.toLowerCase().includes(termo) ||
      produto.codigo.toLowerCase().includes(termo) ||
      (produto.gtin ?? "").includes(termo) ||
      (digitos !== "" && (produto.ncm ?? "").includes(digitos)),
  );

  const semUnidades = unidades.length === 0 && produtos !== null;

  return (
    <Page wide>
      <PageHeader
        title="Produtos"
        description="O catálogo da loja e o saldo de cada item."
        onBack={onBack}
        action={
          <div className="flex gap-2">
            {/* Fora do bloqueio de unidades de propósito: a conferência responde "nada
                para conferir" e isso é melhor que um caminho que não existe. */}
            <Button inline variant="secondary" onClick={onConferencia}>
              Conferência
            </Button>
            {!semUnidades && (
              <>
                <Button inline variant="secondary" onClick={onUnidades}>
                  Unidades
                </Button>
                <Button inline onClick={onNew}>
                  Novo produto
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Sem unidade não há como cadastrar produto. Em vez de deixar o erro acontecer no
          formulário, a tela leva para onde se resolve. */}
      {semUnidades && (
        <Card className="animate-rise border-l-4 border-l-warn-strong">
          <div className="p-6">
            <p className="flex items-center gap-2 text-lg font-semibold text-ink">
              <span aria-hidden="true">⚠</span>
              Falta dizer em que você conta
            </p>
            <p className="mt-2 max-w-prose text-base text-ink-muted">
              Todo produto precisa de uma unidade — peça, quilo, litro. Cadastre a sua
              antes de continuar.
            </p>
            <div className="mt-5">
              <Button inline onClick={onUnidades}>
                Cadastrar unidades
              </Button>
            </div>
          </div>
        </Card>
      )}

      {error && (
        <p
          role="alert"
          className="mb-6 flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger ring-1 ring-inset ring-danger/20"
        >
          <span aria-hidden="true" className="font-bold">
            !
          </span>
          {error}
        </p>
      )}

      {produtos === null && (
        <p className="animate-fade text-base text-ink-muted">Carregando…</p>
      )}

      {produtos !== null && produtos.length > 0 && (
        <>
          <div className="relative mb-5">
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-ink-faint"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.75" />
                <path
                  d="m11 11 3 3"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <input
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por nome, código, código de barras ou NCM"
              aria-label="Buscar produto"
              className="min-h-touch w-full rounded-dk bg-surface pl-11 pr-4 text-base text-ink
                         shadow-xs ring-1 ring-line transition-shadow duration-150 ease-dk
                         placeholder:text-ink-faint hover:ring-ink-faint/40
                         focus:outline-none focus:ring-2 focus:ring-brand-link"
            />
          </div>

          <Card>
            <ul>
              {visiveis.map((produto) => (
                <Row key={produto.id}>
                  <button
                    type="button"
                    onClick={() => onOpen(produto)}
                    className="-m-1 flex min-w-0 flex-1 items-center gap-4 rounded-dk p-1 text-left"
                  >
                    <span
                      aria-hidden="true"
                      className="hidden size-10 shrink-0 items-center justify-center rounded-dk bg-brand-soft text-sm font-semibold text-brand-link sm:flex"
                    >
                      {produto.nome.slice(0, 2).toUpperCase()}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-ink">
                        {produto.nome}
                      </span>
                      <span className="block truncate text-sm text-ink-muted">
                        {produto.codigo}
                        {produto.gtin ? ` · ${produto.gtin}` : ""}
                        {produto.ncm ? ` · NCM ${ncmMask(produto.ncm)}` : ""} ·{" "}
                        {porId.get(produto.unidade_id)?.nome ?? "—"}
                      </span>
                    </span>
                  </button>

                  <div className="flex shrink-0 items-center gap-3">
                    {produto.controla_lote && <Badge tone="info">Lote</Badge>}
                    {produto.preco_venda && (
                      <span className="tabular text-base font-semibold text-ink">
                        R$ {num(produto.preco_venda, 2)}
                      </span>
                    )}
                    <span aria-hidden="true" className="text-ink-faint">
                      ›
                    </span>
                  </div>
                </Row>
              ))}
            </ul>
          </Card>

          {visiveis.length === 0 && (
            <p className="mt-5 text-base text-ink-muted">
              Nenhum produto corresponde a “{busca}”.
            </p>
          )}
        </>
      )}

      {produtos !== null && produtos.length === 0 && unidades.length > 0 && (
        <Card muted>
          <div className="px-6 py-10 text-center">
            <p className="text-base text-ink-muted">
              Nenhum produto cadastrado. Crie o primeiro para começar a controlar o
              estoque.
            </p>
            <div className="mx-auto mt-5 max-w-xs">
              <Button onClick={onNew}>Novo produto</Button>
            </div>
          </div>
        </Card>
      )}
    </Page>
  );
}
