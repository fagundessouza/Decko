import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, Row } from "../components/Card";
import { Modal } from "../components/Modal";
import { TextField } from "../components/TextField";
import { agro } from "../lib/agro";
import type { Piloto } from "../lib/agro";

interface Props {
  onBack: () => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

function ouNulo(valor: string): string | null {
  return valor.trim() === "" ? null : valor.trim();
}

const VAZIO = { nome: "", canac: "", crea: "", cpf: "", telefone: "" };

/* Os pilotos da empresa.
 *
 * Pedido do Nathan em 27/10/2026: antes o nome do piloto só existia como texto dentro da
 * assinatura, redigitado a cada documento. O CREA aparece no formulário porque na
 * AgroDrone a mesma pessoa é o agrônomo e o piloto — ver
 * docs/discovery/agro-planejamento-operacional.md, seção 6.2. */
export function PilotosPage({ onBack }: Props) {
  const [pilotos, setPilotos] = useState<Piloto[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);

  function recarregar() {
    return agro
      .listPilots()
      .then(setPilotos)
      .catch((cause) => {
        setPilotos([]);
        setErro(motivo(cause, "Não foi possível carregar os pilotos."));
      });
  }

  useEffect(() => {
    void recarregar();
  }, []);

  async function salvar() {
    setBusy(true);
    setErro(null);
    try {
      await agro.createPilot({
        nome: form.nome.trim(),
        canac: ouNulo(form.canac),
        crea: ouNulo(form.crea),
        cpf: ouNulo(form.cpf),
        telefone: ouNulo(form.telefone),
      });
      setAberto(false);
      setForm(VAZIO);
      await recarregar();
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível salvar o piloto."));
    } finally {
      setBusy(false);
    }
  }

  const campo = (chave: keyof typeof VAZIO) => ({
    value: form[chave],
    onChange: (event: { target: { value: string } }) =>
      setForm((atual) => ({ ...atual, [chave]: event.target.value })),
  });

  return (
    <Page>
      <PageHeader
        title="Pilotos"
        description="Quem voa pela empresa. O planejamento aponta para o piloto, em vez de repetir o nome."
        onBack={onBack}
        action={
          <Button
            inline
            onClick={() => {
              setForm(VAZIO);
              setErro(null);
              setAberto(true);
            }}
          >
            Novo piloto
          </Button>
        }
      />

      {erro && !aberto && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {pilotos === null && <p className="animate-fade text-base text-ink-muted">Carregando…</p>}

      {pilotos !== null && pilotos.length === 0 && (
        <Card muted>
          <CardBody className="text-center">
            <p className="text-base text-ink-muted">
              Nenhum piloto cadastrado. Cadastre quem voa e o nome para de ser digitado a
              cada planejamento.
            </p>
          </CardBody>
        </Card>
      )}

      {pilotos !== null && pilotos.length > 0 && (
        <Card>
          <ul>
            {pilotos.map((piloto) => (
              <Row key={piloto.id}>
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink">{piloto.nome}</p>
                  <p className="truncate text-sm tabular-nums text-ink-muted">
                    {piloto.canac ? `CANAC ${piloto.canac}` : "Sem código ANAC"}
                    {piloto.crea ? ` · CREA ${piloto.crea}` : ""}
                  </p>
                </div>
                {/* O CREA diz que esta pessoa também assina como agrônomo. */}
                {piloto.crea && <Badge tone="info">Também agrônomo</Badge>}
              </Row>
            ))}
          </ul>
        </Card>
      )}

      <Modal
        open={aberto}
        title="Novo piloto"
        description="O código ANAC é o que sai impresso ao lado da assinatura."
        onClose={() => setAberto(false)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setAberto(false)}>
              Cancelar
            </Button>
            <Button
              inline
              loading={busy}
              disabled={!form.nome.trim()}
              onClick={() => void salvar()}
            >
              Salvar
            </Button>
          </div>
        }
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void salvar();
          }}
        >
          {erro && <Alert tone="danger">{erro}</Alert>}

          <TextField label="Nome" required {...campo("nome")} />
          <TextField
            label="Código ANAC (CANAC)"
            hint="Opcional, mas é o que o formulário imprime."
            inputMode="numeric"
            {...campo("canac")}
          />
          <TextField
            label="CREA"
            hint="Só se esta pessoa também assina como engenheiro agrônomo."
            {...campo("crea")}
          />
          <TextField label="CPF" inputMode="numeric" {...campo("cpf")} />
          <TextField label="Telefone" inputMode="tel" {...campo("telefone")} />
        </form>
      </Modal>
    </Page>
  );
}
