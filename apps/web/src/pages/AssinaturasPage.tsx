import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { assinaturas } from "../lib/assinaturas";
import type { Acesso, Assinatura, Cobranca, Plano } from "../lib/assinaturas";
import { clientes } from "../lib/clientes";
import type { Cliente } from "../lib/clientes";
import { brl } from "../lib/format";

interface Props {
  onBack: () => void;
}

function motivo(causa: unknown, padrao: string): string {
  return causa instanceof Error && causa.message ? causa.message : padrao;
}

function hojeISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function data(iso: string | null): string {
  if (!iso) return "—";
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

/* A ordem da lista é a ordem da preocupação: quem já bloqueou vem antes de quem está em
 * aviso, que vem antes de quem está em dia. Lista alfabética faria o operador procurar o
 * problema, e o problema é o motivo de abrir a tela. */
const PESO: Record<Acesso, number> = { bloqueada: 0, em_aviso: 1, em_dia: 2 };

const ROTULO: Record<Acesso, { texto: string; tom: "danger" | "warn" | "success" }> = {
  bloqueada: { texto: "Bloqueada", tom: "danger" },
  em_aviso: { texto: "Em aviso", tom: "warn" },
  em_dia: { texto: "Em dia", tom: "success" },
};

/* A cobrança que **decide** o estado — a que bloqueia primeiro, não a mais antiga.
 *
 * As duas se confundem quando há uma cobrança em aberto, e divergem quando há várias: dar
 * prazo na mais antiga não muda nada se a do mês passado já estourou sozinha. Mostrar a
 * mais antiga ali fazia o cartão explicar com uma cobrança e marcar o estado por outra —
 * e escrever "bloqueada desde" com uma data no futuro. */
function decisiva(assinatura: Assinatura): Cobranca | null {
  const abertas = assinatura.cobrancas.filter((cobranca) => cobranca.status === "aberta");
  if (abertas.length === 0) return null;
  return [...abertas].sort((a, b) => a.bloqueia_em.localeCompare(b.bloqueia_em))[0];
}

export function AssinaturasPage({ onBack }: Props) {
  const [lista, setLista] = useState<Assinatura[] | null>(null);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [carteira, setCarteira] = useState<Cliente[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [recado, setRecado] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [novaAssinatura, setNovaAssinatura] = useState(false);
  const [novoPlano, setNovoPlano] = useState(false);
  const [baixando, setBaixando] = useState<{ assinatura: Assinatura; cobranca: Cobranca } | null>(
    null,
  );
  const [prazoPara, setPrazoPara] = useState<{
    assinatura: Assinatura;
    cobranca: Cobranca;
  } | null>(null);

  async function recarregar() {
    try {
      const [assinadas, disponiveis] = await Promise.all([
        assinaturas.listar(),
        assinaturas.listarPlanos(),
      ]);
      setLista([...assinadas].sort((a, b) => PESO[a.acesso] - PESO[b.acesso]));
      setPlanos(disponiveis);
    } catch (causa) {
      setLista([]);
      setErro(motivo(causa, "Não foi possível carregar as assinaturas."));
    }
  }

  useEffect(() => {
    let atual = true;
    void recarregar();
    // A carteira só é necessária para assinar; falha aqui não derruba a tela.
    clientes
      .listar()
      .then((achados) => atual && setCarteira(achados))
      .catch(() => atual && setCarteira([]));
    return () => {
      atual = false;
    };
  }, []);

  async function operar(acao: () => Promise<unknown>, padrao: string, sucesso?: string) {
    setBusy(true);
    setErro(null);
    setRecado(null);
    try {
      await acao();
      await recarregar();
      if (sucesso) setRecado(sucesso);
    } catch (causa) {
      setErro(motivo(causa, padrao));
    } finally {
      setBusy(false);
    }
  }

  async function gerarEsteMes() {
    const agora = new Date();
    await operar(async () => {
      const feito = await assinaturas.gerar(agora.getFullYear(), agora.getMonth() + 1);
      // Zero é resposta, não falha: o mês já estava gerado.
      setRecado(
        feito.criadas === 0
          ? "Nada a gerar: as cobranças deste mês já existem."
          : `${feito.criadas} cobrança(s) gerada(s) para este mês.`,
      );
    }, "Não foi possível gerar as cobranças.");
  }

  const emAberto = (lista ?? []).reduce((soma, a) => soma + Number(a.em_aberto), 0);
  const atrasadas = (lista ?? []).filter((a) => a.acesso !== "em_dia");

  return (
    <Page wide>
      <PageHeader
        title="Assinaturas"
        description={
          lista === null
            ? "Carregando…"
            : `${lista.length} ativa(s). ${brl(emAberto)} em aberto.`
        }
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}
      {recado && (
        <div className="mb-6">
          <Alert tone="success">{recado}</Alert>
        </div>
      )}

      {atrasadas.length > 0 && (
        <div className="mb-6">
          <Alert tone="warn" title={`${atrasadas.length} precisa(m) de atenção`}>
            {atrasadas
              .map((a) => `${a.cliente_nome} (${ROTULO[a.acesso].texto.toLowerCase()})`)
              .join(", ")}
          </Alert>
        </div>
      )}

      <div className="mb-8 flex flex-wrap gap-3">
        <Button inline loading={busy} onClick={() => void gerarEsteMes()}>
          Gerar cobranças deste mês
        </Button>
        <Button
          variant="secondary"
          inline
          disabled={busy}
          onClick={() => setNovaAssinatura(true)}
        >
          Nova assinatura
        </Button>
        <Button variant="ghost" inline disabled={busy} onClick={() => setNovoPlano(true)}>
          Novo plano
        </Button>
      </div>

      {lista !== null && lista.length === 0 && (
        <Card muted>
          <p className="px-6 py-10 text-center text-base text-ink-muted">
            Ninguém assina ainda. Crie um plano e depois a primeira assinatura.
          </p>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {(lista ?? []).map((assinatura) => {
          const cobranca = decisiva(assinatura);
          const abertas = assinatura.cobrancas.filter((c) => c.status === "aberta").length;
          const rotulo = ROTULO[assinatura.acesso];

          return (
            <Card key={assinatura.id}>
              <CardHeader
                title={assinatura.cliente_nome}
                description={`${assinatura.plano_nome} · vence dia ${assinatura.dia_vencimento}`}
                action={
                  <Badge tone={rotulo.tom} icon={assinatura.acesso === "em_dia" ? "✓" : "!"}>
                    {rotulo.texto}
                  </Badge>
                }
              />
              <CardBody>
                {cobranca ? (
                  <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
                    <div className="text-base text-ink-muted">
                      <p>
                        <span className="font-medium text-ink">
                          {brl(assinatura.em_aberto)}
                        </span>{" "}
                        em aberto
                        {abertas > 1 && ` em ${abertas} cobranças`}
                      </p>
                      <p className="text-sm">
                        {/* A frase fala da cobrança que decide, e é ela que o botão de
                            prazo recebe — dar prazo em outra não destravaria nada. */}
                        Venceu em {data(cobranca.vencimento)}.{" "}
                        {assinatura.acesso === "bloqueada"
                          ? `Bloqueada desde ${data(cobranca.bloqueia_em)}.`
                          : `Bloqueia em ${data(cobranca.bloqueia_em)}.`}
                        {cobranca.prazo_motivo && (
                          <> Prazo concedido: {cobranca.prazo_motivo}.</>
                        )}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button
                        inline
                        disabled={busy}
                        onClick={() => setBaixando({ assinatura, cobranca })}
                      >
                        Dar baixa
                      </Button>
                      <Button
                        variant="secondary"
                        inline
                        disabled={busy}
                        onClick={() => setPrazoPara({ assinatura, cobranca })}
                      >
                        Dar prazo
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-base text-ink-muted">
                    Nada em aberto.{" "}
                    {assinatura.cobrancas.length === 0 &&
                      "Nenhuma cobrança gerada para esta assinatura ainda."}
                  </p>
                )}
              </CardBody>
            </Card>
          );
        })}
      </div>

      <NovoPlano
        open={novoPlano}
        busy={busy}
        onClose={() => setNovoPlano(false)}
        onSalvar={(corpo) =>
          void operar(
            async () => {
              await assinaturas.criarPlano(corpo);
              setNovoPlano(false);
            },
            "Não foi possível criar o plano.",
            "Plano criado.",
          )
        }
      />

      <NovaAssinatura
        open={novaAssinatura}
        busy={busy}
        planos={planos}
        carteira={carteira}
        onClose={() => setNovaAssinatura(false)}
        onSalvar={(corpo) =>
          void operar(
            async () => {
              await assinaturas.assinar(corpo);
              setNovaAssinatura(false);
            },
            "Não foi possível criar a assinatura.",
            "Assinatura criada.",
          )
        }
      />

      <DarBaixa
        alvo={baixando}
        busy={busy}
        onClose={() => setBaixando(null)}
        onSalvar={(cobrancaId, corpo) =>
          void operar(
            async () => {
              await assinaturas.baixar(cobrancaId, corpo);
              setBaixando(null);
            },
            "Não foi possível dar baixa.",
            "Cobrança baixada.",
          )
        }
      />

      <DarPrazo
        alvo={prazoPara}
        busy={busy}
        onClose={() => setPrazoPara(null)}
        onSalvar={(cobrancaId, corpo) =>
          void operar(
            async () => {
              await assinaturas.concederPrazo(cobrancaId, corpo);
              setPrazoPara(null);
            },
            "Não foi possível conceder o prazo.",
            "Prazo concedido, e registrado na trilha.",
          )
        }
      />
    </Page>
  );
}

function NovoPlano({
  open,
  busy,
  onClose,
  onSalvar,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onSalvar: (corpo: { nome: string; preco_mensal: string; descricao?: string | null }) => void;
}) {
  const [nome, setNome] = useState("");
  const [preco, setPreco] = useState("");

  return (
    <Modal
      open={open}
      title="Novo plano"
      description="O que você vende, e por quanto por mês."
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" inline onClick={onClose}>
            Cancelar
          </Button>
          <Button
            inline
            loading={busy}
            disabled={!nome.trim() || !preco.trim()}
            onClick={() => onSalvar({ nome, preco_mensal: preco.replace(",", ".") })}
          >
            Criar
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <TextField
          label="Nome"
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          placeholder="Mensal, Anual, Balcão…"
        />
        <TextField
          label="Preço por mês"
          leading="R$"
          inputMode="decimal"
          value={preco}
          onChange={(evento) => setPreco(evento.target.value)}
        />
      </div>
    </Modal>
  );
}

function NovaAssinatura({
  open,
  busy,
  planos,
  carteira,
  onClose,
  onSalvar,
}: {
  open: boolean;
  busy: boolean;
  planos: Plano[];
  carteira: Cliente[];
  onClose: () => void;
  onSalvar: (corpo: {
    cliente_id: string;
    plano_id: string;
    inicio: string;
    dia_vencimento: number;
  }) => void;
}) {
  const [clienteId, setClienteId] = useState("");
  const [planoId, setPlanoId] = useState("");
  const [dia, setDia] = useState("10");

  return (
    <Modal
      open={open}
      title="Nova assinatura"
      description="Quem assina, qual plano e em que dia vence."
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" inline onClick={onClose}>
            Cancelar
          </Button>
          <Button
            inline
            loading={busy}
            disabled={!clienteId || !planoId}
            onClick={() =>
              onSalvar({
                cliente_id: clienteId,
                plano_id: planoId,
                inicio: hojeISO(),
                dia_vencimento: Number(dia) || 10,
              })
            }
          >
            Assinar
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <Select
          label="Cliente"
          value={clienteId}
          onChange={setClienteId}
          options={carteira.map((cliente) => ({ value: cliente.id, label: cliente.nome }))}
          placeholder="Escolha quem assina"
          empty="Nenhum cliente cadastrado. Cadastre em Clientes e volte aqui."
        />
        <Select
          label="Plano"
          value={planoId}
          onChange={setPlanoId}
          options={planos
            .filter((plano) => plano.ativo)
            .map((plano) => ({
              value: plano.id,
              label: `${plano.nome} — ${brl(plano.preco_mensal)}`,
            }))}
          placeholder="Escolha o plano"
          empty="Nenhum plano criado ainda."
        />
        <TextField
          label="Dia do vencimento"
          inputMode="numeric"
          value={dia}
          onChange={(evento) => setDia(evento.target.value)}
          hint="De 1 a 28 — para existir em fevereiro também."
        />
      </div>
    </Modal>
  );
}

function DarBaixa({
  alvo,
  busy,
  onClose,
  onSalvar,
}: {
  alvo: { assinatura: Assinatura; cobranca: Cobranca } | null;
  busy: boolean;
  onClose: () => void;
  onSalvar: (
    cobrancaId: string,
    corpo: { pago_em: string; forma_pagamento?: string | null },
  ) => void;
}) {
  const [pagoEm, setPagoEm] = useState(hojeISO());
  const [forma, setForma] = useState("pix");

  return (
    <Modal
      open={alvo !== null}
      title="Dar baixa"
      description={
        alvo ? `${alvo.assinatura.cliente_nome} · ${brl(alvo.cobranca.valor)}` : undefined
      }
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" inline onClick={onClose}>
            Cancelar
          </Button>
          <Button
            inline
            loading={busy}
            onClick={() =>
              alvo && onSalvar(alvo.cobranca.id, { pago_em: pagoEm, forma_pagamento: forma })
            }
          >
            Confirmar recebimento
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <TextField
          label="Recebido em"
          type="date"
          value={pagoEm}
          onChange={(evento) => setPagoEm(evento.target.value)}
        />
        <Select
          label="Forma"
          value={forma}
          onChange={setForma}
          options={[
            { value: "pix", label: "Pix" },
            { value: "boleto", label: "Boleto" },
            { value: "transferencia", label: "Transferência" },
            { value: "dinheiro", label: "Dinheiro" },
            { value: "outro", label: "Outro" },
          ]}
        />
      </div>
    </Modal>
  );
}

function DarPrazo({
  alvo,
  busy,
  onClose,
  onSalvar,
}: {
  alvo: { assinatura: Assinatura; cobranca: Cobranca } | null;
  busy: boolean;
  onClose: () => void;
  onSalvar: (cobrancaId: string, corpo: { ate: string; motivo: string }) => void;
}) {
  // Inicializador preguiçoso: ler o relógio no corpo do render recalcularia a data a cada
  // re-render, e o campo mudaria debaixo de quem está digitando o motivo.
  const [ate, setAte] = useState(() => {
    const amanha = new Date();
    amanha.setDate(amanha.getDate() + 1);
    return amanha.toISOString().slice(0, 10);
  });
  const [razao, setRazao] = useState("");

  return (
    <Modal
      open={alvo !== null}
      title="Dar prazo"
      description={alvo ? `${alvo.assinatura.cliente_nome} · ${brl(alvo.cobranca.valor)}` : undefined}
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" inline onClick={onClose}>
            Cancelar
          </Button>
          <Button
            inline
            loading={busy}
            disabled={!razao.trim()}
            onClick={() => alvo && onSalvar(alvo.cobranca.id, { ate, motivo: razao })}
          >
            Conceder
          </Button>
        </div>
      }
    >
      <p className="mb-4 text-base leading-relaxed text-ink-muted">
        Adia o bloqueio, e só isso: a cobrança continua em aberto. Fica registrado na trilha
        de auditoria com o seu nome.
      </p>

      <div className="flex flex-col gap-4">
        <TextField
          label="Até"
          type="date"
          value={ate}
          onChange={(evento) => setAte(evento.target.value)}
          hint="Precisa ser depois de hoje. Prazo sem fim é dívida perdoada com outro nome."
        />
        <TextField
          label="Motivo"
          value={razao}
          onChange={(evento) => setRazao(evento.target.value)}
          placeholder="Pediu 24h pelo WhatsApp"
          hint="Daqui a três meses, é isto que explica por que houve prazo."
        />
      </div>
    </Modal>
  );
}
