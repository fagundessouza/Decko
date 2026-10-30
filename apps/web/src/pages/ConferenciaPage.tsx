import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Card, CardBody, CardHeader, Row } from "../components/Card";
import { comercial } from "../lib/comercial";
import type { Alertas } from "../lib/comercial";
import { dateBr, num } from "../lib/format";

interface Props {
  onBack: () => void;
}

/* O que está acabando e o que está vencendo, no estoque inteiro.
 *
 * As duas perguntas que o dono não consegue responder olhando produto por produto: uma
 * exige somar a razão de cada item, a outra exige conferir a validade de cada lote com
 * saldo. Por isso a tela existe. */
export function ConferenciaPage({ onBack }: Props) {
  const [alertas, setAlertas] = useState<Alertas | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    comercial
      .alertas()
      .then(setAlertas)
      .catch((cause) =>
        setErro(cause instanceof Error ? cause.message : "Não foi possível conferir."),
      );
  }, []);

  if (erro) {
    return (
      <Page wide>
        <PageHeader title="Conferência" onBack={onBack} />
        <Alert tone="danger">{erro}</Alert>
      </Page>
    );
  }

  if (!alertas) {
    return (
      <Page wide>
        <PageHeader title="Conferência" onBack={onBack} />
        <p className="animate-fade text-base text-ink-muted">Conferindo o estoque…</p>
      </Page>
    );
  }

  return (
    <Page wide>
      <PageHeader
        title="Conferência"
        description="O que está acabando e o que está vencendo."
        onBack={onBack}
      />

      {alertas.total === 0 && (
        <Card muted>
          <CardBody className="text-center">
            <p className="text-base text-ink-muted">
              Nada para conferir agora: nenhum produto abaixo do mínimo e nenhum lote
              vencendo nos próximos {alertas.dias} dias.
            </p>
          </CardBody>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {alertas.acabando.length > 0 && (
          <Card>
            <CardHeader
              title="Está acabando"
              description="Saldo no mínimo que você definiu, ou abaixo dele."
            />
            <ul className="mt-2">
              {alertas.acabando.map((item) => (
                <Row key={item.produto_id}>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{item.nome}</p>
                    <p className="text-sm tabular-nums text-ink-muted">
                      {item.codigo} · mínimo {num(item.estoque_minimo, 3)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Acabar de vez e estar perto de acabar não são a mesma urgência. */}
                    {item.acabou ? (
                      <Badge tone="danger" icon="●">
                        Acabou
                      </Badge>
                    ) : (
                      <Badge tone="warn" icon="▾">
                        Baixo
                      </Badge>
                    )}
                    <span className="tabular font-semibold text-ink">
                      {num(item.saldo, 3)}
                    </span>
                  </div>
                </Row>
              ))}
            </ul>
          </Card>
        )}

        {alertas.vencendo.length > 0 && (
          <Card>
            <CardHeader
              title="Está vencendo"
              description={`Lotes com saldo que vencem nos próximos ${alertas.dias} dias, e os já vencidos.`}
            />
            <ul className="mt-2">
              {alertas.vencendo.map((item) => (
                <Row key={item.lote_id}>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{item.produto_nome}</p>
                    <p className="text-sm tabular-nums text-ink-muted">
                      Lote {item.lote_codigo} · vence {dateBr(item.validade)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {item.vencido ? (
                      <Badge tone="danger" icon="⚠">
                        Vencido
                      </Badge>
                    ) : (
                      <Badge tone="warn" icon="◷">
                        Vence logo
                      </Badge>
                    )}
                    <span className="tabular font-semibold text-ink">
                      {num(item.saldo, 3)}
                    </span>
                  </div>
                </Row>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </Page>
  );
}
