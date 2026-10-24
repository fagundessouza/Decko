import { useEffect, useRef, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, Row } from "../components/Card";
import { compras } from "../lib/compras";
import type { NotaResumo, StatusNota } from "../lib/compras";
import { brl } from "../lib/format";

interface Props {
  onBack: () => void;
  onAbrir: (notaId: string) => void;
}

const TOM: Record<StatusNota, "neutral" | "success" | "warn"> = {
  rascunho: "warn",
  confirmada: "success",
  descartada: "neutral",
};

const ROTULO: Record<StatusNota, string> = {
  rascunho: "A conferir",
  confirmada: "No estoque",
  descartada: "Descartada",
};

/* A lista de notas e a entrada de arquivo.
 *
 * Só o XML entra, e isso é decisão, não limitação temporária: o QR code da NFC-e não
 * contém os itens, e o PDF do DANFE é desenho de impressão. Ver
 * docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md, decisão 6. */
export function NotasPage({ onBack, onAbrir }: Props) {
  const [notas, setNotas] = useState<NotaResumo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const arquivo = useRef<HTMLInputElement>(null);

  function recarregar() {
    return compras
      .listNotas()
      .then(setNotas)
      .catch((cause) => {
        setNotas([]);
        setErro(cause instanceof Error ? cause.message : String(cause));
      });
  }

  useEffect(() => {
    void recarregar();
  }, []);

  async function importar(file: File) {
    setBusy(true);
    setErro(null);
    try {
      const nota = await compras.importar(await file.text());
      await recarregar();
      onAbrir(nota.id);
    } catch (cause) {
      setErro(cause instanceof Error ? cause.message : "Não foi possível ler a nota.");
    } finally {
      setBusy(false);
      // Sem isto, escolher o mesmo arquivo de novo não dispara o evento.
      if (arquivo.current) arquivo.current.value = "";
    }
  }

  return (
    <Page wide>
      <PageHeader
        title="Compras"
        description="Importe o XML da nota do fornecedor e o estoque entra conferido."
        onBack={onBack}
        action={
          <Button
            inline
            loading={busy}
            onClick={() => arquivo.current?.click()}
            icon={<span aria-hidden="true">↑</span>}
          >
            Importar XML
          </Button>
        }
      />

      <input
        ref={arquivo}
        type="file"
        accept=".xml,text/xml,application/xml"
        className="hidden"
        onChange={(event) => {
          const escolhido = event.target.files?.[0];
          if (escolhido) void importar(escolhido);
        }}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {notas !== null && notas.length === 0 && (
        <Card muted>
          <CardBody className="text-center">
            <p className="text-base text-ink-muted">
              Nenhuma nota importada ainda. Escolha o arquivo XML que o fornecedor mandou
              por e-mail.
            </p>
            <p className="mx-auto mt-3 max-w-prose text-sm text-ink-faint">
              O QR code do cupom e o PDF do DANFE ainda não entram: o QR não carrega os
              itens, e ler o PDF depende de reconhecimento de imagem.
            </p>
            <div className="mx-auto mt-6 max-w-xs">
              <Button loading={busy} onClick={() => arquivo.current?.click()}>
                Escolher arquivo
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      {notas !== null && notas.length > 0 && (
        <Card>
          <ul>
            {notas.map((nota) => (
              <Row key={nota.id}>
                <button
                  type="button"
                  onClick={() => onAbrir(nota.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate font-medium text-ink">
                    {nota.emitente_nome ?? nota.emitente_cnpj}
                  </span>
                  <span className="block truncate text-sm text-ink-muted">
                    Nota {nota.numero ?? "—"}
                    {nota.serie ? ` · série ${nota.serie}` : ""}
                  </span>
                </button>

                <div className="flex shrink-0 items-center gap-3">
                  <Badge tone={TOM[nota.status]}>{ROTULO[nota.status]}</Badge>
                  <span className="tabular font-semibold text-ink">
                    {brl(nota.valor_total)}
                  </span>
                </div>
              </Row>
            ))}
          </ul>
        </Card>
      )}

      {notas === null && <p className="animate-fade text-base text-ink-muted">Carregando…</p>}
    </Page>
  );
}
