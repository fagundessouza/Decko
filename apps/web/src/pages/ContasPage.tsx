import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody } from "../components/Card";
import { TextField } from "../components/TextField";
import { financeiro } from "../lib/financeiro";
import type { ContaRecebimento } from "../lib/financeiro";

interface Props {
  onBack: () => void;
}

function motivo(causa: unknown, padrao: string): string {
  return causa instanceof Error && causa.message ? causa.message : padrao;
}

/* Para onde o dinheiro vai.
 *
 * O ponto de venda já diz **como** o cliente pagou. Esta tela existe para a outra
 * pergunta, que é a que não fecha no fim do dia: **em qual conta caiu**. Duas chaves Pix
 * da mesma loja são dois destinos — ver docs/adr/0014-conta-de-recebimento.md.
 *
 * Não é plano de contas: sem saldo, sem extrato, sem conciliação. */
export function ContasPage({ onBack }: Props) {
  const [contas, setContas] = useState<ContaRecebimento[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [nome, setNome] = useState("");
  const [instituicao, setInstituicao] = useState("");
  const [chave, setChave] = useState("");

  async function recarregar() {
    try {
      setContas(await financeiro.listarContas(true));
    } catch (causa) {
      setContas([]);
      setErro(motivo(causa, "Não foi possível carregar as contas."));
    }
  }

  useEffect(() => {
    void recarregar();
  }, []);

  async function operar(acao: () => Promise<unknown>, padrao: string) {
    setBusy(true);
    setErro(null);
    try {
      await acao();
      await recarregar();
    } catch (causa) {
      setErro(motivo(causa, padrao));
    } finally {
      setBusy(false);
    }
  }

  function criar() {
    void operar(async () => {
      await financeiro.criarConta({
        nome,
        instituicao: instituicao || null,
        chave_pix: chave || null,
      });
      setNome("");
      setInstituicao("");
      setChave("");
    }, "Não foi possível criar a conta.");
  }

  return (
    <Page>
      <PageHeader
        title="Contas de recebimento"
        description="Para onde o dinheiro vai. É o que permite fechar o caixa sabendo o que entrou em cada lugar."
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
            className="flex flex-col gap-4"
            onSubmit={(evento) => {
              evento.preventDefault();
              criar();
            }}
          >
            <TextField
              label="Nome"
              value={nome}
              onChange={(evento) => setNome(evento.target.value)}
              placeholder="Nubank PJ, Cofre, Maquininha Stone…"
              hint="Como você chama no dia a dia. É este nome que aparece no caixa."
            />
            <TextField
              label="Instituição"
              value={instituicao}
              onChange={(evento) => setInstituicao(evento.target.value)}
              hint="Opcional."
            />
            <TextField
              label="Chave Pix"
              value={chave}
              onChange={(evento) => setChave(evento.target.value)}
              hint="Opcional. CPF, CNPJ, e-mail, telefone ou aleatória."
            />
            <div>
              <Button type="submit" inline loading={busy} disabled={!nome.trim()}>
                Criar conta
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>

      <div className="mt-8">
        {contas !== null && contas.length === 0 && (
          <Card muted>
            <p className="px-6 py-10 text-center text-base text-ink-muted">
              Nenhuma conta ainda. Sem elas o caixa fecha do mesmo jeito — só não diz onde o
              dinheiro entrou.
            </p>
          </Card>
        )}

        {contas !== null && contas.length > 0 && (
          <Card>
            <ul className="divide-y divide-line">
              {contas.map((conta) => (
                <li
                  key={conta.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6"
                >
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 text-base font-medium text-ink">
                      {conta.nome}
                      {!conta.ativa && <Badge tone="warn">Desativada</Badge>}
                    </p>
                    <p className="truncate text-sm text-ink-faint">
                      {[conta.instituicao, conta.chave_pix].filter(Boolean).join(" · ") ||
                        "Sem instituição ou chave informada."}
                    </p>
                  </div>

                  {/* Desativar tira das escolhas novas; o que já foi recebido continua
                      apontando para ela. Por isso não há "excluir". */}
                  <Button
                    variant="ghost"
                    inline
                    disabled={busy}
                    onClick={() =>
                      void operar(
                        () =>
                          conta.ativa
                            ? financeiro.desativarConta(conta.id)
                            : financeiro.reativarConta(conta.id),
                        "Não foi possível alterar a conta.",
                      )
                    }
                  >
                    {conta.ativa ? "Desativar" : "Reativar"}
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </Page>
  );
}
