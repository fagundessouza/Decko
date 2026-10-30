import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { Select } from "../components/Select";
import { agro } from "../lib/agro";
import type { Consolidation } from "../lib/agro";
import { dateBr, num } from "../lib/format";

const MESES = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

interface Props {
  onBack: () => void;
}

/* Fechamento do mês.
 *
 * Fecha a dor nº 6 do discovery: hoje o mês inteiro é retranscrito do talão para uma
 * planilha. Aqui o mês já está montado, e o CSV abre direto no Excel.
 *
 * Não é o arquivo do portal do MAPA. Qual sistema recebe o envio e em que formato é a
 * questão Q1 do discovery, ainda sem resposta — por isso a tela diz o que está exportando,
 * em vez de deixar a pessoa supor que é o envio oficial. */
type Estado =
  | { fase: "carregando" }
  | { fase: "pronto"; dados: Consolidation }
  | { fase: "erro"; mensagem: string };

export function ConsolidationPage({ onBack }: Props) {
  // Inicialização preguiçosa: `new Date()` a cada render daria um valor novo a cada
  // passagem, e o ano corrente mudaria debaixo da lista.
  const [anoCorrente] = useState(() => new Date().getFullYear());
  const [ano, setAno] = useState(anoCorrente);
  const [mes, setMes] = useState(() => new Date().getMonth() + 1);
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });

  useEffect(() => {
    // Trocar de mês depressa dispara pedidos que podem voltar fora de ordem. Sem esta
    // guarda, a resposta do mês antigo chega depois e sobrescreve a do mês na tela —
    // e o fechamento exibido passa a ser de um período que ninguém pediu.
    let atual = true;
    agro
      .consolidation(ano, mes)
      .then((dados) => {
        if (atual) setEstado({ fase: "pronto", dados });
      })
      .catch((causa) => {
        if (atual) {
          setEstado({
            fase: "erro",
            mensagem: causa instanceof Error ? causa.message : String(causa),
          });
        }
      });
    return () => {
      atual = false;
    };
  }, [ano, mes]);

  // Cinco anos para trás bastam para reabrir um fechamento antigo sem virar uma lista
  // interminável. O ano corrente é o primeiro porque é o que se consulta quase sempre.
  const anos = Array.from({ length: 6 }, (_, i) => anoCorrente - i);
  const dados = estado.fase === "pronto" ? estado.dados : null;

  return (
    <Page wide>
      <PageHeader
        title="Fechamento do mês"
        description="O que foi aplicado no período, pronto para conferência e para a planilha."
        onBack={onBack}
      />

      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex-1">
          <Select
            label="Mês"
            value={String(mes)}
            onChange={(valor) => setMes(Number(valor))}
            placeholder="Selecione"
            options={MESES.map((nome, indice) => ({
              value: String(indice + 1),
              label: nome,
            }))}
          />
        </div>
        <div className="flex-1">
          <Select
            label="Ano"
            value={String(ano)}
            onChange={(valor) => setAno(Number(valor))}
            placeholder="Selecione"
            options={anos.map((valor) => ({ value: String(valor), label: String(valor) }))}
          />
        </div>
      </div>

      {estado.fase === "erro" && (
        <div className="mt-6">
          <Alert tone="danger">{estado.mensagem}</Alert>
        </div>
      )}

      {estado.fase === "carregando" && (
        <p className="mt-6 animate-fade text-base text-ink-muted">Carregando…</p>
      )}

      {dados && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3">
            <Numero titulo="Planejamentos" valor={String(dados.quantidade)} />
            <Numero titulo="Área total" valor={`${num(dados.area_total_ha)} ha`} />
          </div>

          {/* O aviso de deriva vem antes da lista: é o que a empresa precisa ver antes de
              fechar o mês, não depois de ser autuada. */}
          {dados.planos_com_violacao > 0 && (
            <div className="mt-3">
              <Alert tone="warn">
                {dados.planos_com_violacao === 1
                  ? "1 planejamento teve leitura fora dos limites planejados."
                  : `${dados.planos_com_violacao} planejamentos tiveram leitura fora dos limites planejados.`}
              </Alert>
            </div>
          )}

          {dados.planos_sem_data > 0 && (
            <p className="mt-3 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle px-4 py-3 text-base text-ink-muted">
              {dados.planos_sem_data === 1
                ? "1 planejamento está sem data de aplicação e não entra em mês nenhum."
                : `${dados.planos_sem_data} planejamentos estão sem data de aplicação e não entram em mês nenhum.`}
            </p>
          )}

          {dados.totais_por_produto.length > 0 && (
            <section className="mt-6 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle p-5">
              <h2 className="text-lg font-semibold text-ink">Produtos no período</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {dados.totais_por_produto.map((item) => (
                  <li
                    key={item.produto}
                    className="flex items-baseline justify-between gap-3 border-b border-line pb-2 last:border-0"
                  >
                    <span className="text-base text-ink">{item.produto}</span>
                    <span className="text-base font-medium text-ink">{num(item.total, 2)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="mt-6 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle p-5">
            <h2 className="text-lg font-semibold text-ink">Planejamentos</h2>
            {dados.planos.length === 0 ? (
              <p className="mt-2 text-base text-ink-muted">
                Nenhuma aplicação registrada em {MESES[mes - 1].toLowerCase()} de {ano}.
              </p>
            ) : (
              <ul className="mt-4 flex flex-col gap-3">
                {dados.planos.map((plano) => (
                  <li
                    key={plano.id}
                    className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-3 last:border-0"
                  >
                    <div>
                      <p className="text-base font-medium text-ink">
                        Nº {plano.numero} · {dateBr(plano.data_aplicacao)} · {plano.contratante}
                      </p>
                      <p className="text-base text-ink-muted">
                        {plano.propriedade} — {plano.municipio}/{plano.uf} ·{" "}
                        {num(plano.area_ha)} ha
                        {plano.cultura && ` · ${plano.cultura}`}
                      </p>
                      {plano.produtos.length > 0 && (
                        <p className="text-base text-ink-muted">{plano.produtos.join(" · ")}</p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {plano.status !== "assinado" && (
                        <span className="rounded-dk bg-brand-soft px-3 py-1 text-sm font-medium text-ink">
                          {plano.status}
                        </span>
                      )}
                      {plano.violacoes > 0 && (
                        <span className="rounded-dk bg-warn-soft px-3 py-1 text-sm font-medium text-ink">
                          ⚠ {plano.violacoes} fora do limite
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Dois relatórios, e a tela diz qual é qual. Confundir os dois é mandar
              rascunho para o órgão, ou achar que a conferência já prestou contas. */}
          <div className="mt-6 flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <Button
                disabled={dados.quantidade === 0}
                onClick={() => {
                  void agro.downloadMonthlyReport(ano, mes);
                }}
              >
                Baixar relatório do MAPA
              </Button>
              <p className="text-base text-ink-muted">
                Só o que foi realizado, agregado por município, aeronave e tipo de
                atividade — o conteúdo que a Portaria 298/2021 exige. A entrega é pelo
                SIPEAGRO, até o dia 15 do mês seguinte.
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <Button
                variant="ghost"
                disabled={dados.quantidade === 0}
                onClick={() => {
                  void agro.downloadConsolidation(ano, mes);
                }}
              >
                Baixar planilha de conferência
              </Button>
              <p className="text-base text-ink-muted">
                Uma linha por planejamento, com contratante, leituras e o que saiu do
                parâmetro. É para a empresa olhar o mês, não para o órgão.
              </p>
            </div>
          </div>
        </>
      )}
    </Page>
  );
}

function Numero({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div className="rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle px-4 py-4">
      <p className="text-base text-ink-muted">{titulo}</p>
      <p className="mt-1 text-2xl font-bold text-ink">{valor}</p>
    </div>
  );
}
