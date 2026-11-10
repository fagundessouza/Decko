import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { brl } from "../lib/format";
import { pdv } from "../lib/pdv";
import type { Caixa, TipoMovimentoCaixa } from "../lib/pdv";

interface Props {
  onBack: () => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

function horaDe(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/* A sessão de caixa de quem está operando.
 *
 * O esperado não aparece em lugar nenhum enquanto o caixa está aberto — nem na tela, nem
 * na resposta do servidor. A `docs/adr/0008-ponto-de-venda.md` escolheu conferência cega:
 * quem conta vendo o número que deveria dar não confere, confirma. O número só surge
 * depois que a contagem foi enviada.
 *
 * Esta tela é do operador. O relatório do dia, que soma todos os caixas e é do dono, está
 * em `CaixaPage`.
 */
export function MeuCaixaPage({ onBack }: Props) {
  const [caixa, setCaixa] = useState<Caixa | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [abertura, setAbertura] = useState("0,00");

  const [movimentando, setMovimentando] = useState(false);
  const [tipo, setTipo] = useState<TipoMovimentoCaixa>("sangria");
  const [valor, setValor] = useState("");
  const [razao, setRazao] = useState("");

  const [fechando, setFechando] = useState(false);
  const [contado, setContado] = useState("");
  const [fechado, setFechado] = useState<Caixa | null>(null);

  useEffect(() => {
    pdv
      .caixaAberto()
      .then(setCaixa)
      .catch((cause) => setErro(motivo(cause, "Não foi possível ver o caixa.")))
      .finally(() => setCarregando(false));
  }, []);

  async function operar(acao: () => Promise<Caixa>, padrao: string) {
    setBusy(true);
    setErro(null);
    try {
      setCaixa(await acao());
    } catch (cause) {
      setErro(motivo(cause, padrao));
    } finally {
      setBusy(false);
    }
  }

  async function abrir() {
    await operar(
      () => pdv.abrirCaixa(abertura.replace(",", ".") || "0"),
      "Não foi possível abrir o caixa.",
    );
  }

  async function movimentar() {
    if (!caixa) return;
    const corpo = { tipo, valor: valor.replace(",", "."), motivo: razao };
    setMovimentando(false);
    setValor("");
    setRazao("");
    await operar(
      () => pdv.movimentarCaixa(caixa.id, corpo),
      "Não foi possível lançar o movimento.",
    );
  }

  async function fechar() {
    if (!caixa) return;
    const corpo = { contado: contado.replace(",", ".") || "0" };
    setFechando(false);
    setContado("");
    setBusy(true);
    setErro(null);
    try {
      const resultado = await pdv.fecharCaixa(caixa.id, corpo);
      setFechado(resultado);
      setCaixa(null);
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível fechar o caixa."));
    } finally {
      setBusy(false);
    }
  }

  if (carregando) {
    return (
      <Page>
        <PageHeader title="Meu caixa" onBack={onBack} />
        <p className="animate-fade text-base text-ink-muted">Carregando…</p>
      </Page>
    );
  }

  if (fechado) {
    const diferenca = Number(fechado.diferenca ?? 0);
    return (
      <Page>
        <PageHeader title="Caixa fechado" onBack={onBack} />
        <Card>
          <CardBody>
            <dl className="flex flex-col gap-2.5">
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-base text-ink-muted">Contado por você</dt>
                <dd className="text-base tabular-nums text-ink">{brl(fechado.contado)}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-base text-ink-muted">Esperado pelo sistema</dt>
                <dd className="text-base tabular-nums text-ink">{brl(fechado.esperado)}</dd>
              </div>
            </dl>
            <div className="mt-5 border-t border-line-subtle pt-5">
              {Math.abs(diferenca) < 0.005 ? (
                <p className="text-lg font-semibold text-ink">Bateu certo.</p>
              ) : (
                <>
                  <p className="text-sm uppercase tracking-wide text-ink-faint">Diferença</p>
                  <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-ink">
                    {diferenca > 0 ? "sobra de " : "falta de "}
                    {brl(Math.abs(diferenca))}
                  </p>
                  <p className="mt-2 text-sm text-ink-muted">
                    Ficou registrado com o valor contado e o esperado. A diferença não impede
                    fechar — ela é o que a conferência existe para mostrar.
                  </p>
                </>
              )}
            </div>
          </CardBody>
        </Card>
        <div className="mt-6">
          <Button variant="secondary" onClick={() => setFechado(null)}>
            Abrir outro caixa
          </Button>
        </div>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader
        title="Meu caixa"
        description={
          caixa
            ? "Lance retiradas e entradas de dinheiro, e feche contando a gaveta."
            : "Abra o caixa com o fundo de troco. Vender não depende disso."
        }
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {caixa === null ? (
        <Card>
          <CardBody>
            <form
              className="flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                void abrir();
              }}
            >
              <TextField
                label="Fundo de troco"
                leading="R$"
                inputMode="decimal"
                value={abertura}
                onChange={(event) => setAbertura(event.target.value)}
                hint="Quanto já há na gaveta antes da primeira venda. Zero também vale."
              />
              <Button type="submit" loading={busy}>
                Abrir caixa
              </Button>
            </form>
          </CardBody>
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          <Card>
            <CardBody>
              <dl className="flex flex-col gap-2.5">
                <div className="flex items-baseline justify-between gap-4">
                  <dt className="text-base text-ink-muted">Aberto desde</dt>
                  <dd className="text-base tabular-nums text-ink">{horaDe(caixa.aberto_em)}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-4">
                  <dt className="text-base text-ink-muted">Fundo de troco</dt>
                  <dd className="text-base tabular-nums text-ink">{brl(caixa.abertura)}</dd>
                </div>
              </dl>
              {/* Nenhum total de vendas aqui, de propósito: ver o esperado antes de contar
                  transformaria a conferência em confirmação. */}
              <p className="mt-4 text-sm text-ink-muted">
                O quanto deveria haver na gaveta só aparece depois que você contar.
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Retiradas e entradas"
              description={
                caixa.movimentos.length === 0
                  ? "Nada lançado fora de venda ainda."
                  : undefined
              }
              action={
                <Button
                  variant="secondary"
                  inline
                  disabled={busy}
                  onClick={() => setMovimentando(true)}
                >
                  Lançar
                </Button>
              }
            />
            {caixa.movimentos.length > 0 && (
              <ul className="mt-2">
                {caixa.movimentos.map((movimento) => (
                  <li
                    key={movimento.id}
                    className="flex items-center justify-between gap-4 border-b border-line-subtle
                               px-5 py-3 last:border-0 sm:px-6"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-base text-ink">
                        {movimento.tipo === "sangria" ? "Sangria" : "Suprimento"}
                      </span>
                      <span className="block truncate text-sm text-ink-faint">
                        {movimento.motivo}
                      </span>
                    </span>
                    <span className="shrink-0 text-base font-semibold tabular-nums text-ink">
                      {movimento.tipo === "sangria" ? "− " : "+ "}
                      {brl(movimento.valor)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Button loading={busy} onClick={() => setFechando(true)}>
            Fechar caixa
          </Button>
        </div>
      )}

      <Modal
        open={movimentando}
        title="Retirada ou entrada"
        description="Dinheiro que sai ou entra na gaveta fora de venda."
        onClose={() => setMovimentando(false)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setMovimentando(false)}>
              Cancelar
            </Button>
            <Button inline onClick={() => void movimentar()}>
              Lançar movimento
            </Button>
          </div>
        }
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void movimentar();
          }}
        >
          <Select
            label="O que é"
            value={tipo}
            onChange={(valorEscolhido) => setTipo(valorEscolhido as TipoMovimentoCaixa)}
            options={[
              { value: "sangria", label: "Sangria — dinheiro saindo" },
              { value: "suprimento", label: "Suprimento — dinheiro entrando" },
            ]}
          />
          <TextField
            label="Valor"
            leading="R$"
            inputMode="decimal"
            value={valor}
            onChange={(event) => setValor(event.target.value)}
          />
          <TextField
            label="Motivo"
            value={razao}
            onChange={(event) => setRazao(event.target.value)}
            hint="Obrigatório. Retirada que ninguém explica depois é justamente a que importa."
          />
        </form>
      </Modal>

      <Modal
        open={fechando}
        title="Fechar o caixa"
        description="Conte o dinheiro da gaveta e digite o quanto encontrou."
        onClose={() => setFechando(false)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setFechando(false)}>
              Cancelar
            </Button>
            <Button inline onClick={() => void fechar()}>
              Confirmar fechamento
            </Button>
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void fechar();
          }}
        >
          <TextField
            label="Quanto há na gaveta"
            leading="R$"
            inputMode="decimal"
            value={contado}
            onChange={(event) => setContado(event.target.value)}
            hint="Só o dinheiro em espécie. A diferença não impede fechar."
          />
        </form>
      </Modal>
    </Page>
  );
}
