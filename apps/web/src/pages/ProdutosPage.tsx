import { useEffect, useState } from "react";

import { Button } from "../components/Button";
import { comercial } from "../lib/comercial";
import type { Produto, Unidade } from "../lib/comercial";
import { num } from "../lib/format";

interface Props {
  onBack: () => void;
  onOpen: (produto: Produto) => void;
  onNew: () => void;
  onUnidades: () => void;
}

export function ProdutosPage({ onBack, onOpen, onNew, onUnidades }: Props) {
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
  const visiveis = (produtos ?? []).filter(
    (produto) =>
      !termo ||
      produto.nome.toLowerCase().includes(termo) ||
      produto.codigo.toLowerCase().includes(termo) ||
      (produto.gtin ?? "").includes(termo),
  );

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <button
        type="button"
        onClick={onBack}
        className="min-h-touch text-base font-medium text-brand-link"
      >
        ← Voltar
      </button>

      <h1 className="mt-2 text-3xl font-bold text-ink">Produtos</h1>

      {/* Sem unidade não há como cadastrar produto. Em vez de deixar o erro acontecer no
          formulário, a tela leva para onde se resolve. */}
      {unidades.length === 0 && produtos !== null && (
        <div className="mt-6 rounded-dk border-2 border-warn bg-warn-soft px-4 py-4">
          <p className="text-lg font-bold text-ink">
            <span aria-hidden="true">⚠ </span>
            Falta dizer em que você conta
          </p>
          <p className="mt-1 text-base text-ink">
            Todo produto precisa de uma unidade — peça, quilo, litro. Cadastre a sua antes
            de continuar.
          </p>
          <div className="mt-4">
            <Button onClick={onUnidades}>Cadastrar unidades</Button>
          </div>
        </div>
      )}

      {unidades.length > 0 && (
        <div className="mt-6 flex flex-col gap-3">
          <Button onClick={onNew}>Novo produto</Button>
          <button
            type="button"
            onClick={onUnidades}
            className="min-h-touch text-base font-medium text-brand-link"
          >
            Unidades e embalagens
          </button>
        </div>
      )}

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

      {produtos === null && <p className="mt-6 text-lg text-ink-muted">Carregando…</p>}

      {produtos !== null && produtos.length > 0 && (
        <>
          <input
            type="search"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por nome, código ou código de barras"
            aria-label="Buscar produto"
            className="mt-6 min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink placeholder:text-ink-muted/70 focus:border-brand-link focus:outline-none"
          />

          <ul className="mt-4 flex flex-col gap-3">
            {visiveis.map((produto) => (
              <li key={produto.id}>
                <button
                  type="button"
                  onClick={() => onOpen(produto)}
                  className="min-h-touch w-full rounded-dk border border-line bg-surface px-5 py-4 text-left hover:border-brand-link"
                >
                  <p className="text-xl font-semibold text-ink">{produto.nome}</p>
                  <p className="text-base text-ink-muted">
                    {produto.codigo}
                    {produto.gtin ? ` · ${produto.gtin}` : ""} ·{" "}
                    {porId.get(produto.unidade_id)?.nome ?? "—"}
                    {produto.preco_venda ? ` · R$ ${num(produto.preco_venda, 2)}` : ""}
                  </p>
                  {produto.controla_lote && (
                    <p className="mt-1 text-sm text-ink-muted">Controla lote</p>
                  )}
                </button>
              </li>
            ))}
          </ul>

          {visiveis.length === 0 && (
            <p className="mt-4 text-lg text-ink-muted">
              Nenhum produto corresponde a “{busca}”.
            </p>
          )}
        </>
      )}

      {produtos !== null && produtos.length === 0 && unidades.length > 0 && (
        <p className="mt-6 rounded-dk border border-line bg-surface px-5 py-6 text-lg text-ink-muted">
          Nenhum produto cadastrado. Crie o primeiro para começar a controlar o estoque.
        </p>
      )}
    </div>
  );
}
