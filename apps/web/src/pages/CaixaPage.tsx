import { useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { TextField } from "../components/TextField";
import { brl, todayLocal } from "../lib/format";
import { FORMAS, pdv } from "../lib/pdv";
import type { Conferencia } from "../lib/pdv";

interface Props {
  onBack: () => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

function rotuloDaForma(valor: string): string {
  return FORMAS.find((forma) => forma.valor === valor)?.label ?? valor;
}

/** O dia inteiro, em instantes do fuso de quem está olhando. */
function limitesDoDia(dia: string): { de: Date; ate: Date } {
  return { de: new Date(`${dia}T00:00:00`), ate: new Date(`${dia}T23:59:59.999`) };
}

function Linha({
  rotulo,
  valor,
  destaque = false,
}: {
  rotulo: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className={destaque ? "text-base font-medium text-ink" : "text-base text-ink-muted"}>
        {rotulo}
      </dt>
      <dd
        className={
          "tabular-nums " + (destaque ? "text-lg font-semibold text-ink" : "text-base text-ink")
        }
      >
        {valor}
      </dd>
    </div>
  );
}

/* A conferência de caixa.
 *
 * A contagem vem **antes** do esperado, e isso não é detalhe de interface: é a decisão da
 * `docs/adr/0008-ponto-de-venda.md`, que escolheu conferência cega. Quem conta vendo o
 * número que deveria dar não está conferindo — está confirmando. Por isso o valor da
 * gaveta é pedido primeiro e só então o resto aparece.
 *
 * Conta-se **só o dinheiro em espécie**, porque é o que está na gaveta. Cartão e Pix
 * aparecem somados, para leitura, e não para contagem: conferir o que não se conta é
 * ruído. Se a loja quiser conferir também a maquininha, isso é requisito e está na
 * pergunta 4 do `docs/discovery/pdv-fechamento-de-caixa.md`.
 *
 * Esta tela **não fecha caixa**: ela mostra. Abrir, fechar, sangria e suprimento dependem
 * de regra que varia por loja e que ninguém escreveu ainda.
 */
export function CaixaPage({ onBack }: Props) {
  const [dia, setDia] = useState(todayLocal());
  const [contado, setContado] = useState("");
  const [resultado, setResultado] = useState<Conferencia | null>(null);
  const [contadoNaHora, setContadoNaHora] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function conferir() {
    setBusy(true);
    setErro(null);
    try {
      const { de, ate } = limitesDoDia(dia);
      const dados = await pdv.conferencia(de, ate);
      // Guardado no momento do clique: mudar o campo depois não altera o que foi contado.
      setContadoNaHora(contado.replace(",", "."));
      setResultado(dados);
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível conferir o caixa."));
      setResultado(null);
    } finally {
      setBusy(false);
    }
  }

  function recomeçar() {
    setResultado(null);
    setContado("");
    setContadoNaHora("");
  }

  const emEspecie = resultado?.por_forma.find((linha) => linha.forma === "dinheiro");
  const esperado = Number(emEspecie?.valor ?? 0);
  const diferenca = contadoNaHora === "" ? null : Number(contadoNaHora) - esperado;

  return (
    <Page>
      <PageHeader
        title="Conferência de caixa"
        description="Conte o dinheiro da gaveta antes de ver o que o sistema esperava."
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {resultado === null ? (
        <Card>
          <CardBody>
            <form
              className="flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                void conferir();
              }}
            >
              <TextField
                label="Dia"
                type="date"
                value={dia}
                onChange={(event) => setDia(event.target.value)}
              />
              <TextField
                label="Quanto há na gaveta"
                leading="R$"
                inputMode="decimal"
                autoFocus
                value={contado}
                onChange={(event) => setContado(event.target.value)}
                hint="Só o dinheiro em espécie. Cartão e Pix aparecem depois, somados."
              />
              <Button type="submit" loading={busy} disabled={contado.trim() === ""}>
                Conferir
              </Button>
            </form>
          </CardBody>
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="O dinheiro da gaveta" />
            <CardBody className="pt-4">
              <dl className="flex flex-col gap-2.5">
                <Linha rotulo="Contado por você" valor={brl(contadoNaHora)} />
                <Linha rotulo="Esperado pelo sistema" valor={brl(esperado)} />
              </dl>
              <div className="mt-5 border-t border-line-subtle pt-5">
                {diferenca !== null && Math.abs(diferenca) < 0.005 ? (
                  <p className="text-lg font-semibold text-ink">Bateu certo.</p>
                ) : (
                  <>
                    <p className="text-sm uppercase tracking-wide text-ink-faint">Diferença</p>
                    <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-ink">
                      {diferenca !== null && diferenca > 0 ? "sobra de " : "falta de "}
                      {brl(Math.abs(diferenca ?? 0))}
                    </p>
                    {/* A divergência é informação, não acusação: dizer o que ela pode ser
                        evita que o operador a esconda na próxima vez. */}
                    <p className="mt-2 text-sm text-ink-muted">
                      Pode ser troco dado errado, venda não lançada, ou dinheiro retirado da
                      gaveta durante o dia — retirada ainda não é registrada pelo sistema.
                    </p>
                  </>
                )}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="O que entrou no dia" />
            <CardBody className="pt-4">
              <dl className="flex flex-col gap-2.5">
                <Linha rotulo="Vendas fechadas" valor={String(resultado.vendas)} />
                <Linha rotulo="Soma dos itens" valor={brl(resultado.bruto)} />
                {Number(resultado.descontos) > 0 && (
                  <Linha rotulo="Descontos" valor={`− ${brl(resultado.descontos)}`} />
                )}
                <Linha rotulo="Total das vendas" valor={brl(resultado.liquido)} destaque />
                <Linha rotulo="Recebido" valor={brl(resultado.recebido)} />
                {resultado.canceladas > 0 && (
                  <Linha rotulo="Canceladas" valor={String(resultado.canceladas)} />
                )}
              </dl>
            </CardBody>
          </Card>

          {resultado.por_forma.length > 0 && (
            <Card>
              <CardHeader title="Por forma de pagamento" />
              <CardBody className="pt-4">
                <dl className="flex flex-col gap-2.5">
                  {resultado.por_forma.map((linha) => (
                    <Linha
                      key={linha.forma}
                      rotulo={`${rotuloDaForma(linha.forma)} (${linha.quantidade})`}
                      valor={brl(linha.valor)}
                    />
                  ))}
                </dl>
              </CardBody>
            </Card>
          )}

          {resultado.por_conta.length > 0 && (
            <Card>
              <CardHeader title="Por conta de recebimento" />
              <CardBody className="pt-4">
                <dl className="flex flex-col gap-2.5">
                  {resultado.por_conta.map((linha) => (
                    <Linha
                      key={linha.conta_id ?? "sem-conta"}
                      rotulo={linha.conta_nome ?? "Sem conta informada"}
                      valor={brl(linha.valor)}
                    />
                  ))}
                </dl>
              </CardBody>
            </Card>
          )}

          {resultado.por_operador.length > 0 && (
            <Card>
              <CardHeader title="Por operador" />
              <CardBody className="pt-4">
                <dl className="flex flex-col gap-2.5">
                  {resultado.por_operador.map((linha) => (
                    <Linha
                      key={linha.operador_id ?? "sem-operador"}
                      rotulo={`${linha.operador_nome ?? "Sem operador"} (${linha.vendas})`}
                      valor={brl(linha.valor)}
                    />
                  ))}
                </dl>
              </CardBody>
            </Card>
          )}

          <Button variant="secondary" onClick={recomeçar}>
            Conferir outro dia
          </Button>
        </div>
      )}
    </Page>
  );
}
