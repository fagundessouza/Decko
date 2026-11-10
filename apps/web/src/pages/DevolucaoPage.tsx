import { useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { brl, num } from "../lib/format";
import { DESTINOS, FORMAS, pdv } from "../lib/pdv";
import type {
  DestinoDevolucao,
  Devolucao,
  DevolucoesDaVenda,
  FormaPagamento,
  LinhaDevolvivel,
  PreviaDevolucao,
} from "../lib/pdv";

interface Props {
  onBack: () => void;
}

function motivoDoErro(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

function rotuloDoDestino(destino: DestinoDevolucao): string {
  return DESTINOS.find((d) => d.valor === destino)?.label ?? destino;
}

function ajudaDoDestino(destino: DestinoDevolucao): string {
  return DESTINOS.find((d) => d.valor === destino)?.ajuda ?? "";
}

/* A devolução de uma venda.
 *
 * Duas coisas aqui não são detalhe de interface:
 *
 * 1. **O valor vem do servidor, antes de a gaveta abrir.** O operador pede a prévia e vê
 *    quanto sai; a prévia passa pela mesma conta que a gravação, então o número que ele
 *    confirma é o número que sai. A tela não soma dinheiro — ADR 0008, decisão 3.
 * 2. **Defeito é dito por linha.** O que volta para vender entra no estoque; o que tem
 *    defeito não entra, e fica na lista de avarias. Não existe depósito de avaria, e o
 *    porquê está em `docs/discovery/pdv-devolucao-de-venda.md`.
 */
export function DevolucaoPage({ onBack }: Props) {
  const [numero, setNumero] = useState("");
  const [venda, setVenda] = useState<DevolucoesDaVenda | null>(null);

  const [quantidades, setQuantidades] = useState<Record<string, string>>({});
  const [destinos, setDestinos] = useState<Record<string, DestinoDevolucao>>({});
  const [forma, setForma] = useState<FormaPagamento>("dinheiro");
  const [razao, setRazao] = useState("");

  const [previa, setPrevia] = useState<PreviaDevolucao | null>(null);
  const [feita, setFeita] = useState<Devolucao | null>(null);

  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function limpar() {
    setQuantidades({});
    setDestinos({});
    setRazao("");
    setPrevia(null);
  }

  async function buscar() {
    setBusy(true);
    setErro(null);
    setVenda(null);
    limpar();
    try {
      const achadas = await pdv.porNumero(Number(numero));
      const finalizada = achadas.find((v) => v.status === "finalizada");
      if (!finalizada) {
        // Dizer qual é o caso: venda aberta se cancela, e cupom errado se redigita.
        setErro(
          achadas.length === 0
            ? `Não há venda com o número ${numero}.`
            : "Essa venda não está finalizada, então não há o que devolver.",
        );
        return;
      }
      setVenda(await pdv.devolucoesDaVenda(finalizada.id));
    } catch (cause) {
      setErro(motivoDoErro(cause, "Não foi possível buscar a venda."));
    } finally {
      setBusy(false);
    }
  }

  function destinoDe(linha: LinhaDevolvivel): DestinoDevolucao {
    return destinos[linha.venda_item_id] ?? "estoque";
  }

  function escolhidos() {
    if (!venda) return [];
    return venda.linhas
      .map((linha) => ({
        venda_item_id: linha.venda_item_id,
        quantidade: (quantidades[linha.venda_item_id] ?? "").replace(",", "."),
        destino: destinoDe(linha),
      }))
      .filter((linha) => Number(linha.quantidade) > 0);
  }

  function devolverTudo() {
    if (!venda) return;
    const cheio: Record<string, string> = {};
    for (const linha of venda.linhas) {
      if (Number(linha.resta) > 0) cheio[linha.venda_item_id] = num(linha.resta, 6);
    }
    setQuantidades(cheio);
  }

  async function prever() {
    if (!venda) return;
    setBusy(true);
    setErro(null);
    try {
      setPrevia(await pdv.preverDevolucao(venda.venda_id, escolhidos()));
    } catch (cause) {
      setErro(motivoDoErro(cause, "Não foi possível calcular a devolução."));
    } finally {
      setBusy(false);
    }
  }

  async function devolver() {
    if (!venda) return;
    setPrevia(null);
    setBusy(true);
    setErro(null);
    try {
      const devolucao = await pdv.devolver(venda.venda_id, {
        itens: escolhidos(),
        forma,
        motivo: razao,
      });
      setFeita(devolucao);
      setVenda(null);
      limpar();
    } catch (cause) {
      setErro(motivoDoErro(cause, "Não foi possível registrar a devolução."));
    } finally {
      setBusy(false);
    }
  }

  if (feita) {
    const avariados = feita.itens.filter((item) => item.destino === "avaria");
    return (
      <Page>
        <PageHeader title="Devolução registrada" onBack={onBack} />
        <Card>
          <CardBody>
            <p className="text-sm uppercase tracking-wide text-ink-faint">Devolvido ao cliente</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-ink">
              {brl(feita.total)}
            </p>
            <p className="mt-2 text-base text-ink-muted">
              Em {FORMAS.find((f) => f.valor === feita.forma)?.label ?? feita.forma}.
              {feita.caixa_id === null
                ? " Registrada fora de sessão de caixa."
                : " Lançada no seu caixa aberto."}
            </p>
            {avariados.length > 0 && (
              <p className="mt-4 border-t border-line-subtle pt-4 text-base text-ink-muted">
                {avariados.length === 1 ? "Um item" : `${avariados.length} itens`} com defeito
                não voltou ao estoque, e está na lista de avarias da conferência do dia.
              </p>
            )}
          </CardBody>
        </Card>
        <div className="mt-6">
          <Button
            variant="secondary"
            onClick={() => {
              setFeita(null);
              setNumero("");
            }}
          >
            Outra devolução
          </Button>
        </div>
      </Page>
    );
  }

  const nenhum = escolhidos().length === 0;

  return (
    <Page>
      <PageHeader
        title="Devolução de venda"
        description="Ache a venda pelo número do cupom e diga o que está voltando."
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <Card>
        <CardBody>
          <form
            className="flex flex-col gap-4 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              void buscar();
            }}
          >
            <div className="flex-1">
              <TextField
                label="Número do cupom"
                inputMode="numeric"
                autoFocus
                value={numero}
                onChange={(event) => setNumero(event.target.value)}
                hint="O número que saiu na venda."
              />
            </div>
            <Button type="submit" loading={busy} disabled={numero.trim() === ""}>
              Buscar venda
            </Button>
          </form>
        </CardBody>
      </Card>

      {venda && (
        <div className="mt-6 flex flex-col gap-6">
          <Card>
            <CardHeader
              title={`Venda ${venda.numero ?? "—"}`}
              description={`Custou ${brl(venda.total)}${
                Number(venda.devolvido) > 0 ? ` · já devolvido ${brl(venda.devolvido)}` : ""
              }`}
              action={
                <Button variant="secondary" inline disabled={busy} onClick={devolverTudo}>
                  Devolver tudo
                </Button>
              }
            />
            <CardBody className="pt-4">
              <div className="flex flex-col gap-6">
                {venda.linhas.map((linha) => {
                  const resta = Number(linha.resta);
                  if (resta <= 0) {
                    return (
                      <p key={linha.venda_item_id} className="text-base text-ink-faint">
                        {linha.descricao} — já devolvido por inteiro.
                      </p>
                    );
                  }
                  return (
                    <div key={linha.venda_item_id} className="flex flex-col gap-3">
                      <TextField
                        label={`${linha.descricao} — quantas voltam`}
                        inputMode="decimal"
                        value={quantidades[linha.venda_item_id] ?? ""}
                        onChange={(event) =>
                          setQuantidades({
                            ...quantidades,
                            [linha.venda_item_id]: event.target.value,
                          })
                        }
                        hint={
                          `Vendidas ${num(linha.quantidade, 6)}` +
                          `${Number(linha.devolvida) > 0 ? `, já voltaram ${num(linha.devolvida, 6)}` : ""}` +
                          `. Resta devolver ${num(linha.resta, 6)}, até ${brl(linha.valor_resta)}.`
                        }
                      />
                      <Select
                        label={`${linha.descricao} — o que fazer`}
                        value={destinoDe(linha)}
                        onChange={(escolhido) =>
                          setDestinos({
                            ...destinos,
                            [linha.venda_item_id]: escolhido as DestinoDevolucao,
                          })
                        }
                        options={DESTINOS.map((destino) => ({
                          value: destino.valor,
                          label: destino.label,
                        }))}
                        hint={ajudaDoDestino(destinoDe(linha))}
                      />
                    </div>
                  );
                })}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Como o dinheiro volta" />
            <CardBody className="pt-4">
              <div className="flex flex-col gap-4">
                <Select
                  label="Forma"
                  value={forma}
                  onChange={(escolhida) => setForma(escolhida as FormaPagamento)}
                  options={FORMAS.map((f) => ({ value: f.valor, label: f.label }))}
                  hint={
                    forma === "dinheiro"
                      ? "Sai da gaveta, e o fechamento do caixa já conta com isso."
                      : "Fica registrado nesta forma. O estorno em si é da adquirente."
                  }
                />
                <TextField
                  label="Motivo"
                  value={razao}
                  onChange={(event) => setRazao(event.target.value)}
                  hint="Obrigatório. Devolução que ninguém explica depois é a que importa explicar."
                />
              </div>
            </CardBody>
          </Card>

          <Button
            loading={busy}
            disabled={nenhum || razao.trim() === ""}
            onClick={() => void prever()}
          >
            Ver quanto devolve
          </Button>

          {venda.devolucoes.length > 0 && (
            <Card>
              <CardHeader title="Devoluções anteriores desta venda" />
              <ul className="mt-2">
                {venda.devolucoes.map((devolucao) => (
                  <li
                    key={devolucao.id}
                    className="flex items-center justify-between gap-4 border-b border-line-subtle
                               px-5 py-3 last:border-0 sm:px-6"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-base text-ink">{devolucao.motivo}</span>
                      <span className="block truncate text-sm text-ink-faint">
                        {devolucao.itens
                          .map(
                            (item) =>
                              `${num(item.quantidade, 6)} · ${rotuloDoDestino(item.destino)}`,
                          )
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="shrink-0 text-base font-semibold tabular-nums text-ink">
                      {brl(devolucao.total)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      <Modal
        open={previa !== null}
        title="Confirmar a devolução"
        description="Este é o valor conferido pelo servidor. Devolver mexe no estoque e no caixa."
        onClose={() => setPrevia(null)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setPrevia(null)}>
              Cancelar
            </Button>
            <Button inline onClick={() => void devolver()}>
              Confirmar devolução
            </Button>
          </div>
        }
      >
        <p className="text-sm uppercase tracking-wide text-ink-faint">Devolver ao cliente</p>
        <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-ink">
          {brl(previa?.total)}
        </p>
        <p className="mt-2 text-base text-ink-muted">
          Em {FORMAS.find((f) => f.valor === forma)?.label ?? forma}.
          {forma === "dinheiro" ? " Sai da gaveta." : " Registrado nesta forma."}
        </p>
      </Modal>
    </Page>
  );
}
