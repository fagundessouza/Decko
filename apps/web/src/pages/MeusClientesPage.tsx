import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, Row } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { plataforma } from "../lib/api";
import type { EmpresaDaPlataforma } from "../lib/api";
import { clientes, comoEntrada } from "../lib/clientes";
import type { Cliente } from "../lib/clientes";
import { dateBr } from "../lib/format";

interface Props {
  onBack: () => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* As empresas que usam o Decko, e qual contato da carteira é cada uma.
 *
 * Em 13/11/2026 a primeira empresa cliente entrou — Agrodrone — e não aparecia em lugar
 * nenhum: `tenant` é tabela da plataforma, e a carteira de clientes vive dentro da
 * empresa. Eram dois lados da fronteira de isolamento sem nada ligando. Ver
 * docs/adr/0021-nivel-de-plataforma.md.
 *
 * A tela mostra **só o que a tabela `tenant` já diz**. Módulos ativos, movimento e gente
 * de cada empresa ficam de fora de propósito: ler de dentro de empresa alheia é
 * travessia, e travessia é decisão própria, com motivo próprio (decisão 3). */
export function MeusClientesPage({ onBack }: Props) {
  const [empresas, setEmpresas] = useState<EmpresaDaPlataforma[] | null>(null);
  /* Nulo aqui quer dizer "não deu para ler a carteira", e não "está vazia": sem o módulo
   * de clientes nesta conta, a lista de empresas continua valendo por si. */
  const [carteira, setCarteira] = useState<Cliente[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ligando, setLigando] = useState<EmpresaDaPlataforma | null>(null);
  const [escolhido, setEscolhido] = useState("");
  const [busy, setBusy] = useState(false);

  function recarregar() {
    return Promise.all([
      plataforma
        .empresas()
        .then(setEmpresas)
        .catch((cause) => {
          setEmpresas([]);
          setErro(motivo(cause, "Não foi possível carregar as empresas."));
        }),
      clientes
        .listar(undefined, true)
        .then(setCarteira)
        .catch(() => setCarteira(null)),
    ]);
  }

  useEffect(() => {
    void recarregar();
  }, []);

  const contatoDe = (empresa: EmpresaDaPlataforma): Cliente | undefined =>
    carteira?.find((cliente) => cliente.tenant_assinante_id === empresa.id);

  // Quem ainda não é empresa nenhuma. Uma empresa é apontada por um contato só, e por
  // isso quem já aponta para outra não entra na lista de escolha.
  const livres = (carteira ?? []).filter((cliente) => cliente.tenant_assinante_id === null);

  async function ligar() {
    const empresa = ligando;
    const cliente = (carteira ?? []).find((item) => item.id === escolhido);
    if (!empresa || !cliente) return;

    setBusy(true);
    setErro(null);
    try {
      await clientes.atualizar(
        cliente.id,
        comoEntrada(cliente, { tenant_assinante_id: empresa.id }),
      );
      setLigando(null);
      await recarregar();
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível ligar o contato a esta empresa."));
    } finally {
      setBusy(false);
    }
  }

  async function desligar(cliente: Cliente) {
    setBusy(true);
    setErro(null);
    try {
      await clientes.atualizar(cliente.id, comoEntrada(cliente, { tenant_assinante_id: null }));
      await recarregar();
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível desligar o contato."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page>
      <PageHeader
        title="Meus clientes"
        description="As empresas que usam o Decko. Ligue cada uma ao contato da carteira para saber quem paga por qual acesso."
        onBack={onBack}
      />

      {erro && !ligando && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {carteira === null && empresas !== null && (
        <div className="mb-6">
          <Alert tone="info">
            Esta conta não tem a carteira de clientes instalada, então as empresas aparecem
            sem o contato que as paga.
          </Alert>
        </div>
      )}

      {empresas === null && <p className="animate-fade text-base text-ink-muted">Carregando…</p>}

      {empresas !== null && empresas.length === 0 && !erro && (
        <Card muted>
          <CardBody className="text-center">
            <p className="text-base text-ink-muted">
              Nenhuma empresa na plataforma. Empresa nasce pela linha de comando do
              servidor, com <code className="font-mono text-sm">decko-admin bootstrap</code>.
            </p>
          </CardBody>
        </Card>
      )}

      {empresas !== null && empresas.length > 0 && (
        <Card>
          <ul>
            {empresas.map((empresa) => {
              const contato = contatoDe(empresa);
              return (
                <Row key={empresa.id}>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{empresa.name}</p>
                    <p className="truncate text-sm text-ink-muted">
                      <span className="font-mono">{empresa.slug}</span>
                      {` · entrou em ${dateBr(empresa.created_at.slice(0, 10))}`}
                    </p>
                    {contato && (
                      <p className="truncate text-sm text-ink-muted">
                        Cobrada no contato <span className="text-ink">{contato.nome}</span>
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {!empresa.is_active && <Badge tone="warn">Desativada</Badge>}
                    {contato ? (
                      <Button
                        variant="secondary"
                        inline
                        disabled={busy}
                        onClick={() => void desligar(contato)}
                      >
                        Desligar
                      </Button>
                    ) : (
                      <Button
                        variant="secondary"
                        inline
                        disabled={carteira === null}
                        onClick={() => {
                          setEscolhido("");
                          setErro(null);
                          setLigando(empresa);
                        }}
                      >
                        Ligar a um contato
                      </Button>
                    )}
                  </div>
                </Row>
              );
            })}
          </ul>
        </Card>
      )}

      <Modal
        open={ligando !== null}
        title={`Ligar ${ligando?.name ?? ""} a um contato`}
        description="É o que liga quem usa o Decko a quem o Decko cobra. A assinatura continua sendo do contato."
        onClose={() => setLigando(null)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setLigando(null)}>
              Cancelar
            </Button>
            <Button inline loading={busy} disabled={!escolhido} onClick={() => void ligar()}>
              Ligar
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          {erro && <Alert tone="danger">{erro}</Alert>}

          <Select
            label="Contato da carteira"
            hint="Cada empresa é apontada por um contato só."
            options={livres.map((cliente) => ({ value: cliente.id, label: cliente.nome }))}
            value={escolhido}
            onChange={setEscolhido}
            placeholder="Escolha o contato"
            empty="Nenhum contato livre na carteira. Cadastre a empresa em Clientes primeiro."
          />
        </div>
      </Modal>
    </Page>
  );
}
