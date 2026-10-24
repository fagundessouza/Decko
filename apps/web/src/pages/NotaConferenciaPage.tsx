import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Select } from "../components/Select";
import { comercial, describeUnidade } from "../lib/comercial";
import type { Unidade } from "../lib/comercial";
import { compras, explicarVinculo } from "../lib/compras";
import type { Candidato, Nota, NotaItem } from "../lib/compras";
import { brl, ncmMask, num } from "../lib/format";

interface Props {
  notaId: string;
  onBack: () => void;
  /** Depois de confirmar: o estoque mudou, e quem estiver olhando precisa saber. */
  onConfirmada: () => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* A conferência da nota.
 *
 * O que o fornecedor escreveu fica à vista de um lado; o que isso vira no cadastro, do
 * outro. O que o código de barras resolveu já vem ligado; o que é palpite de nome espera
 * o clique — ver docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md. */
export function NotaConferenciaPage({ notaId, onBack, onConfirmada }: Props) {
  const [nota, setNota] = useState<Nota | null>(null);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feito, setFeito] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([compras.ver(notaId), comercial.listUnidades()])
      .then(([carregada, lista]) => {
        setNota(carregada);
        setUnidades(lista);
      })
      .catch((cause) => setErro(motivo(cause, "Não foi possível abrir a nota.")));
  }, [notaId]);

  const raiz = unidades.find((unidade) => unidade.referencia_id === null);

  async function operar(acao: () => Promise<Nota>, padrao: string) {
    setBusy(true);
    setErro(null);
    try {
      setNota(await acao());
    } catch (cause) {
      setErro(motivo(cause, padrao));
    } finally {
      setBusy(false);
    }
  }

  async function confirmar() {
    if (!nota) return;
    setBusy(true);
    setErro(null);
    try {
      const resultado = await compras.confirmar(nota.id);
      setFeito(
        `${resultado.itens_lancados} ${resultado.itens_lancados === 1 ? "item lançado" : "itens lançados"}` +
          (resultado.produtos_criados > 0
            ? `, ${resultado.produtos_criados} produto${resultado.produtos_criados === 1 ? "" : "s"} cadastrado${resultado.produtos_criados === 1 ? "" : "s"}.`
            : "."),
      );
      setNota(await compras.ver(nota.id));
      onConfirmada();
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível confirmar a nota."));
    } finally {
      setBusy(false);
    }
  }

  if (!nota) {
    return (
      <Page wide>
        <PageHeader title="Conferir nota" onBack={onBack} />
        {erro ? (
          <Alert tone="danger">{erro}</Alert>
        ) : (
          <p className="animate-fade text-base text-ink-muted">Carregando…</p>
        )}
      </Page>
    );
  }

  const aberta = nota.status === "rascunho";

  return (
    <Page wide>
      <PageHeader
        title={nota.emitente_nome ?? nota.emitente_cnpj}
        description={`Nota ${nota.numero ?? "—"} · ${brl(nota.valor_total)}`}
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {feito && (
        <div className="mb-6">
          <Alert tone="success">{feito}</Alert>
        </div>
      )}

      {aberta && nota.pendentes > 0 && (
        <div className="mb-6">
          <Alert tone="info">
            {nota.pendentes === 1
              ? "Falta dizer o que é 1 item desta nota."
              : `Faltam dizer o que são ${nota.pendentes} itens desta nota.`}{" "}
            Nada entra no estoque antes disso.
          </Alert>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {nota.itens.map((item) => (
          <ItemCard
            key={item.id}
            item={item}
            unidades={unidades}
            raiz={raiz}
            editavel={aberta}
            busy={busy}
            onVincular={(produtoId, unidadeId) =>
              void operar(
                () =>
                  compras.vincular(nota.id, item.id, {
                    produto_id: produtoId,
                    unidade_id: unidadeId,
                  }),
                "Não foi possível ligar o item ao produto.",
              )
            }
            onNovo={(unidadeId) =>
              void operar(
                () => compras.marcarComoNovo(nota.id, item.id, unidadeId),
                "Não foi possível marcar como produto novo.",
              )
            }
          />
        ))}
      </div>

      {aberta && (
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button
            variant="ghost"
            inline
            disabled={busy}
            onClick={() =>
              void operar(
                async () => {
                  await compras.descartar(nota.id);
                  return compras.ver(nota.id);
                },
                "Não foi possível descartar a nota.",
              )
            }
          >
            Descartar nota
          </Button>
          <Button
            inline
            loading={busy}
            disabled={nota.pendentes > 0}
            onClick={() => void confirmar()}
          >
            Dar entrada no estoque
          </Button>
        </div>
      )}
    </Page>
  );
}

function ItemCard({
  item,
  unidades,
  raiz,
  editavel,
  busy,
  onVincular,
  onNovo,
}: {
  item: NotaItem;
  unidades: Unidade[];
  raiz: Unidade | undefined;
  editavel: boolean;
  busy: boolean;
  onVincular: (produtoId: string, unidadeId: string | null) => void;
  onNovo: (unidadeId: string) => void;
}) {
  // A nota diz "CX"; quantas unidades tem a caixa, ela não diz. Quem sabe é o lojista.
  const [unidadeId, setUnidadeId] = useState(item.unidade_id ?? raiz?.id ?? "");
  const resolvido = item.produto_id !== null || item.origem_vinculo === "novo";

  return (
    <Card>
      <CardHeader
        title={item.descricao}
        description={`${item.codigo_fornecedor} · ${num(item.quantidade, 3)} ${
          item.unidade_comercial ?? ""
        } · ${brl(item.valor_unitario)} cada`}
        action={
          resolvido ? (
            <Badge tone="success" icon="✓">
              {item.origem_vinculo === "novo" ? "Produto novo" : "Reconhecido"}
            </Badge>
          ) : (
            <Badge tone="warn" icon="?">
              Falta dizer
            </Badge>
          )
        }
      />

      <CardBody className="pt-4">
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-faint">
          {item.gtin ? (
            <span className="tabular">Código de barras {item.gtin}</span>
          ) : (
            <span>Sem código de barras na nota</span>
          )}
          {item.ncm && <span className="tabular">NCM {ncmMask(item.ncm)}</span>}
        </p>

        {resolvido && (
          <p className="mt-3 text-sm text-ink-muted">{explicarVinculo(item.origem_vinculo)}</p>
        )}

        {editavel && !resolvido && (
          <div className="mt-5 flex flex-col gap-4">
            <div className="max-w-sm">
              <Select
                label="Contado em"
                hint="A nota não diz quantas unidades vêm na embalagem."
                value={unidadeId}
                onChange={setUnidadeId}
                options={unidades.map((unidade) => ({
                  value: unidade.id,
                  label: describeUnidade(unidade, raiz),
                }))}
                empty="Cadastre uma unidade antes."
              />
            </div>

            {item.sugestoes.length > 0 && (
              <div>
                <p className="text-sm font-medium text-ink">É algum destes?</p>
                <p className="mb-3 text-sm text-ink-faint">
                  Parecido pelo nome. O sistema não liga sozinho por semelhança.
                </p>
                <ul className="flex flex-col gap-2">
                  {item.sugestoes.map((candidato) => (
                    <li key={candidato.produto_id}>
                      <Sugestao
                        candidato={candidato}
                        busy={busy}
                        onEscolher={() => onVincular(candidato.produto_id, unidadeId || null)}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="sm:max-w-xs">
              <Button
                variant="secondary"
                disabled={busy || !unidadeId}
                onClick={() => unidadeId && onNovo(unidadeId)}
              >
                Cadastrar como produto novo
              </Button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Sugestao({
  candidato,
  busy,
  onEscolher,
}: {
  candidato: Candidato;
  busy: boolean;
  onEscolher: () => void;
}) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onEscolher}
      className="flex w-full items-center justify-between gap-4 rounded-dk px-4 py-3 text-left
                 ring-1 ring-line-subtle transition-colors duration-150 ease-dk
                 hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span className="min-w-0 truncate text-base text-ink">{candidato.nome}</span>
      <span className="tabular shrink-0 text-sm text-ink-faint">
        {Math.round(candidato.pontuacao * 100)}% parecido
      </span>
    </button>
  );
}
