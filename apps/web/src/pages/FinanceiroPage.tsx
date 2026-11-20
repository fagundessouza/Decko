import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { comercial } from "../lib/comercial";
import type { Produto, Unidade } from "../lib/comercial";
import { custos as apiCustos } from "../lib/custos";
import type {
  Consumo as ConsumoRegistrado,
  ConsumoBody,
  CustoDoCentro,
} from "../lib/custos";
import { brl, dateBr, num, todayLocal } from "../lib/format";
import { financeiro } from "../lib/financeiro";
import type {
  CentroDeCusto,
  Conta,
  Despesa,
  ResumoFinanceiro,
} from "../lib/financeiro";

interface Props {
  onBack: () => void;
  /** Com o módulo de custo instalado, a quebra deixa de ser só de despesa e passa a somar
   *  o que saiu do estoque. Sem ele, a seção continua existindo — só não conhece consumo. */
  temCustos?: boolean;
}

function motivo(causa: unknown, padrao: string): string {
  return causa instanceof Error && causa.message ? causa.message : padrao;
}

/** O primeiro e o último dia do mês da data dada, em ISO. */
function mesDe(iso: string): { de: string; ate: string } {
  const [ano, mes] = iso.split("-").map(Number);
  const ultimo = new Date(ano, mes, 0).getDate();
  const dois = (n: number) => String(n).padStart(2, "0");
  return { de: `${ano}-${dois(mes)}-01`, ate: `${ano}-${dois(mes)}-${dois(ultimo)}` };
}

function deslocarMes(iso: string, passos: number): string {
  const [ano, mes] = iso.split("-").map(Number);
  const data = new Date(ano, mes - 1 + passos, 1);
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-01`;
}

const MESES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

function nomeDoMes(iso: string): string {
  const [ano, mes] = iso.split("-").map(Number);
  return `${MESES[mes - 1]} de ${ano}`;
}

/* O dinheiro da empresa, numa tela só.
 *
 * Conta de recebimento e centro de custo são cadastro, e cadastro não merece tela
 * própria: quem abre o financeiro quer saber o que vence, e só às vezes quer mexer na
 * lista de contas. Por isso tudo acontece aqui, em diálogo — inclusive cadastrar um
 * centro no meio do lançamento, sem perder o que já foi digitado.
 *
 * Decisões: docs/adr/0014-conta-de-recebimento.md, 0024-contas-a-pagar.md e
 * 0025-centro-de-custo.md. */
export function FinanceiroPage({ onBack, temCustos = false }: Props) {
  const [mes, setMes] = useState(() => mesDe(todayLocal()).de);
  const [despesas, setDespesas] = useState<Despesa[] | null>(null);
  const [resumo, setResumo] = useState<ResumoFinanceiro | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [centros, setCentros] = useState<CentroDeCusto[]>([]);
  const [porCentro, setPorCentro] = useState<CustoDoCentro[]>([]);
  const [consumos, setConsumos] = useState<ConsumoRegistrado[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [lancando, setLancando] = useState(false);
  const [baixando, setBaixando] = useState<Despesa | null>(null);
  const [cancelando, setCancelando] = useState<Despesa | null>(null);
  const [cadastros, setCadastros] = useState(false);
  const [novoCentro, setNovoCentro] = useState(false);
  const [novaConta, setNovaConta] = useState(false);
  const [lancandoConsumo, setLancandoConsumo] = useState(false);
  const [vendoConsumos, setVendoConsumos] = useState(false);

  const periodo = mesDe(mes);

  async function recarregar() {
    try {
      const [lista, totais, c, cc] = await Promise.all([
        financeiro.listarDespesas({ de: periodo.de, ate: periodo.ate }),
        financeiro.resumo(periodo.de, periodo.ate),
        financeiro.listarContas(true),
        financeiro.listarCentros(true),
      ]);
      setDespesas(lista);
      setResumo(totais);
      setContas(c);
      setCentros(cc);
      /* Em chamada separada e tolerante a falha: o custo somado é um extra, e perder o
         módulo de custos não pode apagar a lista do que vence. */
      setPorCentro(temCustos ? await apiCustos.porCentro(periodo.de, periodo.ate) : []);
      setConsumos(
        temCustos ? await apiCustos.listarConsumos(periodo.de, periodo.ate) : [],
      );
    } catch (causa) {
      setDespesas([]);
      setErro(motivo(causa, "Não foi possível carregar o financeiro."));
    }
  }

  useEffect(() => {
    void recarregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mes, temCustos]);

  async function operar(acao: () => Promise<unknown>, padrao: string) {
    setBusy(true);
    setErro(null);
    try {
      await acao();
      await recarregar();
      return true;
    } catch (causa) {
      setErro(motivo(causa, padrao));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page>
      <PageHeader
        title="Financeiro"
        description="O que vence, o que já saiu, e contra o quê. As contas e os centros de custo ficam no botão ao lado."
        onBack={onBack}
        action={
          <Button variant="secondary" inline onClick={() => setCadastros(true)}>
            Contas e centros
          </Button>
        }
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            inline
            aria-label="Mês anterior"
            onClick={() => setMes(deslocarMes(mes, -1))}
          >
            ←
          </Button>
          <span className="min-w-44 text-center text-base font-medium text-ink">
            {nomeDoMes(mes)}
          </span>
          <Button
            variant="ghost"
            inline
            aria-label="Próximo mês"
            onClick={() => setMes(deslocarMes(mes, 1))}
          >
            →
          </Button>
        </div>
        <Button inline onClick={() => setLancando(true)}>
          Lançar despesa
        </Button>
      </div>

      {resumo && (
        <div className="mb-8 grid gap-4 sm:grid-cols-3">
          <Card>
            <CardBody>
              <p className="text-sm text-ink-muted">A pagar no mês</p>
              <p className="mt-1 text-2xl font-semibold text-ink">{brl(resumo.em_aberto)}</p>
              <p className="mt-1 text-sm text-ink-faint">
                {resumo.quantidade_em_aberto === 1
                  ? "1 conta em aberto"
                  : `${resumo.quantidade_em_aberto} contas em aberto`}
              </p>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <p className="text-sm text-ink-muted">Vencido</p>
              <p className="mt-1 text-2xl font-semibold text-ink">{brl(resumo.vencido)}</p>
              <p className="mt-1 text-sm text-ink-faint">Passou do prazo e não foi pago.</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <p className="text-sm text-ink-muted">Já saiu</p>
              <p className="mt-1 text-2xl font-semibold text-ink">{brl(resumo.pago)}</p>
              <p className="mt-1 text-sm text-ink-faint">
                O que de fato foi pago, com juros ou desconto.
              </p>
            </CardBody>
          </Card>
        </div>
      )}

      {despesas !== null && despesas.length === 0 && (
        <Card muted>
          <p className="px-6 py-10 text-center text-base text-ink-muted">
            Nada vencendo em {nomeDoMes(mes)}.
          </p>
        </Card>
      )}

      {despesas !== null && despesas.length > 0 && (
        <Card>
          <ul className="divide-y divide-line">
            {despesas.map((despesa) => (
              <li
                key={despesa.id}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6"
              >
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 text-base font-medium text-ink">
                    {despesa.descricao}
                    {despesa.status === "paga" && <Badge tone="ok">Paga</Badge>}
                    {despesa.status === "cancelada" && (
                      <Badge tone="warn">Cancelada</Badge>
                    )}
                  </p>
                  <p className="truncate text-sm text-ink-faint">
                    {[
                      `vence ${dateBr(despesa.vencimento)}`,
                      despesa.fornecedor_nome,
                      centros.find((c) => c.id === despesa.centro_custo_id)?.nome,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-base font-medium text-ink">
                    {brl(despesa.status === "paga" ? despesa.valor_pago : despesa.valor)}
                  </span>
                  {despesa.status === "aberta" && (
                    <>
                      <Button inline disabled={busy} onClick={() => setBaixando(despesa)}>
                        Dar baixa
                      </Button>
                      <Button
                        variant="ghost"
                        inline
                        disabled={busy}
                        onClick={() => setCancelando(despesa)}
                      >
                        Cancelar
                      </Button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {temCustos && (
        <div className="mt-8">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-ink">Quanto custou cada centro</h2>
            <div className="flex items-center gap-2">
              <Button variant="ghost" inline onClick={() => setVendoConsumos(true)}>
                Ver consumos
              </Button>
              <Button variant="secondary" inline onClick={() => setLancandoConsumo(true)}>
                Lançar consumo
              </Button>
            </div>
          </div>
          <p className="mb-3 text-sm text-ink-muted">
            O que saiu do estoque mais o que foi pago em despesa. É uma estimativa pelo
            preço de custo do produto, e não um custo contábil.
          </p>
          <Card>
            <ul className="divide-y divide-line">
              {porCentro.map((linha) => (
                <li key={linha.centro_id} className="px-5 py-3 sm:px-6">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-base text-ink">{linha.nome}</span>
                    <span className="text-base font-medium text-ink">{brl(linha.total)}</span>
                  </div>
                  <p className="text-sm text-ink-faint">
                    {brl(linha.consumo)} de estoque · {brl(linha.despesa)} de despesa
                  </p>
                </li>
              ))}
            </ul>
          </Card>
          {porCentro.length === 0 && (
            <Card muted>
              <p className="px-6 py-8 text-center text-base text-ink-muted">
                Nada lançado contra centro de custo neste mês. Lance um consumo, ou escolha
                um centro ao criar a despesa.
              </p>
            </Card>
          )}
        </div>
      )}

      {!temCustos && resumo && resumo.por_centro.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-base font-semibold text-ink">Contra o quê</h2>
          <Card>
            <ul className="divide-y divide-line">
              {resumo.por_centro.map((linha) => (
                <li
                  key={linha.centro_id ?? "sem-centro"}
                  className="flex items-center justify-between gap-3 px-5 py-3 sm:px-6"
                >
                  <span className="text-base text-ink">{linha.nome}</span>
                  <span className="text-sm text-ink-muted">
                    {brl(linha.em_aberto)} a pagar · {brl(linha.pago)} pago
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      <LancarDespesa
        aberto={lancando}
        busy={busy}
        centros={centros.filter((c) => c.ativo)}
        onNovoCentro={() => setNovoCentro(true)}
        onFechar={() => setLancando(false)}
        onLancar={async (body) => {
          if (await operar(() => financeiro.lancarDespesa(body), "Não foi possível lançar.")) {
            setLancando(false);
          }
        }}
      />

      <DarBaixa
        despesa={baixando}
        busy={busy}
        contas={contas.filter((c) => c.ativa)}
        onNovaConta={() => setNovaConta(true)}
        onFechar={() => setBaixando(null)}
        onBaixar={async (body) => {
          if (
            baixando &&
            (await operar(
              () => financeiro.baixarDespesa(baixando.id, body),
              "Não foi possível dar baixa.",
            ))
          ) {
            setBaixando(null);
          }
        }}
      />

      <Modal
        open={cancelando !== null}
        title="Esta conta não será paga?"
        description="Ela continua na lista, marcada como cancelada. Nada é apagado."
        onClose={() => setCancelando(null)}
        footer={
          <div className="flex justify-end gap-3">
            <Button variant="ghost" inline onClick={() => setCancelando(null)}>
              Voltar
            </Button>
            <Button
              variant="danger"
              inline
              loading={busy}
              onClick={async () => {
                if (
                  cancelando &&
                  (await operar(
                    () => financeiro.cancelarDespesa(cancelando.id),
                    "Não foi possível cancelar.",
                  ))
                ) {
                  setCancelando(null);
                }
              }}
            >
              Cancelar a conta
            </Button>
          </div>
        }
      >
        <p className="text-base text-ink-muted">
          {cancelando?.descricao} · {brl(cancelando?.valor ?? "0")}
        </p>
      </Modal>

      <LancarConsumo
        aberto={lancandoConsumo}
        busy={busy}
        centros={centros.filter((c) => c.ativo)}
        onNovoCentro={() => setNovoCentro(true)}
        onFechar={() => setLancandoConsumo(false)}
        onLancar={async (body) => {
          if (
            await operar(
              () => apiCustos.registrarConsumo(body),
              "Não foi possível lançar o consumo.",
            )
          ) {
            setLancandoConsumo(false);
          }
        }}
      />

      <ConsumosDoMes
        aberto={vendoConsumos}
        consumos={consumos}
        onFechar={() => setVendoConsumos(false)}
      />

      <Cadastros
        aberto={cadastros}
        busy={busy}
        contas={contas}
        centros={centros}
        onFechar={() => setCadastros(false)}
        operar={operar}
      />

      {/* Submodais: cadastrar sem perder o que já foi digitado no diálogo de baixo. */}
      <NovoCentro
        aberto={novoCentro}
        busy={busy}
        onFechar={() => setNovoCentro(false)}
        onCriar={async (nome) => {
          if (await operar(() => financeiro.criarCentro(nome), "Não foi possível criar.")) {
            setNovoCentro(false);
          }
        }}
      />

      <NovaConta
        aberto={novaConta}
        busy={busy}
        onFechar={() => setNovaConta(false)}
        onCriar={async (nome) => {
          if (
            await operar(() => financeiro.criarConta({ nome }), "Não foi possível criar.")
          ) {
            setNovaConta(false);
          }
        }}
      />
    </Page>
  );
}

// ------------------------------------------------------------------ lançar

function LancarDespesa({
  aberto,
  busy,
  centros,
  onNovoCentro,
  onFechar,
  onLancar,
}: {
  aberto: boolean;
  busy: boolean;
  centros: CentroDeCusto[];
  onNovoCentro: () => void;
  onFechar: () => void;
  onLancar: (body: {
    descricao: string;
    valor: string;
    vencimento: string;
    fornecedor_nome: string | null;
    centro_custo_id: string | null;
  }) => void;
}) {
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [vencimento, setVencimento] = useState(todayLocal());
  const [fornecedor, setFornecedor] = useState("");
  const [centro, setCentro] = useState("");

  useEffect(() => {
    if (aberto) {
      setDescricao("");
      setValor("");
      setVencimento(todayLocal());
      setFornecedor("");
      setCentro("");
    }
  }, [aberto]);

  return (
    <Modal
      open={aberto}
      title="Lançar despesa"
      description="O que se deve, para quem, e quando vence."
      onClose={onFechar}
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="ghost" inline onClick={onFechar}>
            Voltar
          </Button>
          <Button
            inline
            loading={busy}
            disabled={!descricao.trim() || !valor.trim()}
            onClick={() =>
              onLancar({
                descricao,
                valor,
                vencimento,
                fornecedor_nome: fornecedor || null,
                centro_custo_id: centro || null,
              })
            }
          >
            Lançar
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <TextField
          label="Descrição"
          value={descricao}
          onChange={(evento) => setDescricao(evento.target.value)}
          placeholder="Energia da sede, arrendamento, parcela do trator…"
        />
        <TextField
          label="Valor"
          leading="R$"
          inputMode="decimal"
          value={valor}
          onChange={(evento) => setValor(evento.target.value)}
          placeholder="480,00"
        />
        <TextField
          label="Vencimento"
          type="date"
          value={vencimento}
          onChange={(evento) => setVencimento(evento.target.value)}
        />
        <TextField
          label="Fornecedor"
          value={fornecedor}
          onChange={(evento) => setFornecedor(evento.target.value)}
          hint="Opcional. Quem recebe."
        />

        <div className="flex flex-col gap-2">
          <Select
            label="Centro de custo"
            value={centro}
            onChange={setCentro}
            placeholder="Sem centro de custo"
            options={centros.map((c) => ({ value: c.id, label: c.nome }))}
            hint="Opcional. É o que responde, no fim da safra, contra o quê o dinheiro saiu."
            empty="Nenhum centro de custo ainda."
          />
          <div>
            <Button variant="ghost" inline onClick={onNovoCentro}>
              + Novo centro de custo
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ baixar

function DarBaixa({
  despesa,
  busy,
  contas,
  onNovaConta,
  onFechar,
  onBaixar,
}: {
  despesa: Despesa | null;
  busy: boolean;
  contas: Conta[];
  onNovaConta: () => void;
  onFechar: () => void;
  onBaixar: (body: {
    pago_em: string;
    valor_pago: string | null;
    conta_id: string | null;
  }) => void;
}) {
  const [pagoEm, setPagoEm] = useState(todayLocal());
  const [valorPago, setValorPago] = useState("");
  const [conta, setConta] = useState("");

  useEffect(() => {
    if (despesa) {
      setPagoEm(todayLocal());
      setValorPago("");
      setConta("");
    }
  }, [despesa]);

  return (
    <Modal
      open={despesa !== null}
      title="Dar baixa"
      description="Depois disso ela não volta atrás: dinheiro que saiu, saiu."
      onClose={onFechar}
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="ghost" inline onClick={onFechar}>
            Voltar
          </Button>
          <Button
            inline
            loading={busy}
            onClick={() =>
              onBaixar({
                pago_em: pagoEm,
                valor_pago: valorPago || null,
                conta_id: conta || null,
              })
            }
          >
            Marcar como paga
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-base text-ink-muted">
          {despesa?.descricao} · devido {brl(despesa?.valor ?? "0")}
        </p>
        <TextField
          label="Pago em"
          type="date"
          value={pagoEm}
          onChange={(evento) => setPagoEm(evento.target.value)}
        />
        <TextField
          label="Valor pago"
          leading="R$"
          inputMode="decimal"
          value={valorPago}
          onChange={(evento) => setValorPago(evento.target.value)}
          placeholder={despesa?.valor ?? ""}
          hint="Em branco, vale o que se devia. Preencha quando houve juros, multa ou desconto."
        />

        <div className="flex flex-col gap-2">
          <Select
            label="Saiu de qual conta"
            value={conta}
            onChange={setConta}
            placeholder="Não informar"
            options={contas.map((c) => ({ value: c.id, label: c.nome }))}
            hint="Opcional."
            empty="Nenhuma conta cadastrada ainda."
          />
          <div>
            <Button variant="ghost" inline onClick={onNovaConta}>
              + Nova conta
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ submodais

function NovoCentro({
  aberto,
  busy,
  onFechar,
  onCriar,
}: {
  aberto: boolean;
  busy: boolean;
  onFechar: () => void;
  onCriar: (nome: string) => void;
}) {
  const [nome, setNome] = useState("");

  useEffect(() => {
    if (aberto) setNome("");
  }, [aberto]);

  return (
    <Modal
      open={aberto}
      nested
      title="Novo centro de custo"
      description="Lavoura, pecuária, frota, administrativo."
      onClose={onFechar}
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="ghost" inline onClick={onFechar}>
            Voltar
          </Button>
          <Button inline loading={busy} disabled={!nome.trim()} onClick={() => onCriar(nome)}>
            Criar
          </Button>
        </div>
      }
    >
      <TextField
        label="Nome"
        value={nome}
        onChange={(evento) => setNome(evento.target.value)}
        hint="É por este nome que a quebra de custo aparece."
      />
    </Modal>
  );
}

function NovaConta({
  aberto,
  busy,
  onFechar,
  onCriar,
}: {
  aberto: boolean;
  busy: boolean;
  onFechar: () => void;
  onCriar: (nome: string) => void;
}) {
  const [nome, setNome] = useState("");

  useEffect(() => {
    if (aberto) setNome("");
  }, [aberto]);

  return (
    <Modal
      open={aberto}
      nested
      title="Nova conta"
      description="Banco, chave Pix, ou a gaveta do caixa."
      onClose={onFechar}
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="ghost" inline onClick={onFechar}>
            Voltar
          </Button>
          <Button inline loading={busy} disabled={!nome.trim()} onClick={() => onCriar(nome)}>
            Criar
          </Button>
        </div>
      }
    >
      <TextField
        label="Nome"
        value={nome}
        onChange={(evento) => setNome(evento.target.value)}
        placeholder="Nubank PJ, Cofre, Maquininha Stone…"
      />
    </Modal>
  );
}

// ------------------------------------------------------------------ cadastros

function Cadastros({
  aberto,
  busy,
  contas,
  centros,
  onFechar,
  operar,
}: {
  aberto: boolean;
  busy: boolean;
  contas: Conta[];
  centros: CentroDeCusto[];
  onFechar: () => void;
  operar: (acao: () => Promise<unknown>, padrao: string) => Promise<boolean>;
}) {
  const [conta, setConta] = useState("");
  const [instituicao, setInstituicao] = useState("");
  const [chave, setChave] = useState("");
  const [centro, setCentro] = useState("");

  return (
    <Modal
      open={aberto}
      largura="ampla"
      title="Contas e centros de custo"
      description="Onde o dinheiro está, e contra o quê ele sai. Nada aqui se apaga: desativa."
      onClose={onFechar}
    >
      <div className="grid gap-8 sm:grid-cols-2">
        <section>
          <h3 className="mb-3 text-base font-semibold text-ink">Contas</h3>
          <form
            className="flex flex-col gap-3"
            onSubmit={async (evento) => {
              evento.preventDefault();
              if (
                await operar(
                  () =>
                    financeiro.criarConta({
                      nome: conta,
                      instituicao: instituicao || null,
                      chave_pix: chave || null,
                    }),
                  "Não foi possível criar a conta.",
                )
              ) {
                setConta("");
                setInstituicao("");
                setChave("");
              }
            }}
          >
            <TextField
              label="Nome"
              value={conta}
              onChange={(evento) => setConta(evento.target.value)}
              placeholder="Nubank PJ, Cofre…"
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
              <Button type="submit" inline loading={busy} disabled={!conta.trim()}>
                Criar conta
              </Button>
            </div>
          </form>

          <ul className="mt-5 divide-y divide-line">
            {contas.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-3">
                <span className="flex min-w-0 items-center gap-2 text-base text-ink">
                  <span className="truncate">{item.nome}</span>
                  {!item.ativa && <Badge tone="warn">Desativada</Badge>}
                </span>
                <Button
                  variant="ghost"
                  inline
                  disabled={busy}
                  onClick={() =>
                    void operar(
                      () =>
                        item.ativa
                          ? financeiro.desativarConta(item.id)
                          : financeiro.reativarConta(item.id),
                      "Não foi possível alterar a conta.",
                    )
                  }
                >
                  {item.ativa ? "Desativar" : "Reativar"}
                </Button>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="mb-3 text-base font-semibold text-ink">Centros de custo</h3>
          <form
            className="flex flex-col gap-3"
            onSubmit={async (evento) => {
              evento.preventDefault();
              if (
                await operar(
                  () => financeiro.criarCentro(centro),
                  "Não foi possível criar o centro.",
                )
              ) {
                setCentro("");
              }
            }}
          >
            <TextField
              label="Nome"
              value={centro}
              onChange={(evento) => setCentro(evento.target.value)}
              placeholder="Lavoura, pecuária, frota…"
              hint="Lista plana: sem pai, sem código contábil."
            />
            <div>
              <Button type="submit" inline loading={busy} disabled={!centro.trim()}>
                Criar centro
              </Button>
            </div>
          </form>

          <ul className="mt-5 divide-y divide-line">
            {centros.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-3">
                <span className="flex min-w-0 items-center gap-2 text-base text-ink">
                  <span className="truncate">{item.nome}</span>
                  {!item.ativo && <Badge tone="warn">Desativado</Badge>}
                </span>
                <Button
                  variant="ghost"
                  inline
                  disabled={busy}
                  onClick={() =>
                    void operar(
                      () =>
                        item.ativo
                          ? financeiro.desativarCentro(item.id)
                          : financeiro.reativarCentro(item.id),
                      "Não foi possível alterar o centro.",
                    )
                  }
                >
                  {item.ativo ? "Desativar" : "Reativar"}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ consumo de estoque

/* Lançar consumo mora aqui, e não numa tela sua.
 *
 * É o mesmo assunto da seção de custo logo acima: o que saiu do estoque sem ser venda.
 * Mandar quem está olhando "quanto custou a lavoura" para outra tela só para lançar o
 * adubo quebraria o raciocínio no meio. Ver docs/BRAND.md, seção 8. */
function LancarConsumo({
  aberto,
  busy,
  centros,
  onNovoCentro,
  onFechar,
  onLancar,
}: {
  aberto: boolean;
  busy: boolean;
  centros: CentroDeCusto[];
  onNovoCentro: () => void;
  onFechar: () => void;
  onLancar: (body: ConsumoBody) => void;
}) {
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [busca, setBusca] = useState("");
  const [produtoId, setProdutoId] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [unidadeId, setUnidadeId] = useState("");
  const [centro, setCentro] = useState("");
  const [valor, setValor] = useState("");
  const [observacao, setObservacao] = useState("");

  /* O catálogo só é baixado quando o diálogo abre: peso de abertura é requisito, e quem
     veio ver o que vence não deve pagar pela lista de produtos. */
  useEffect(() => {
    if (!aberto) return;
    setBusca("");
    setProdutoId("");
    setQuantidade("");
    setCentro("");
    setValor("");
    setObservacao("");
    void comercial.listUnidades().then(setUnidades).catch(() => setUnidades([]));
  }, [aberto]);

  useEffect(() => {
    if (!aberto) return;
    let valeu = true;
    void comercial
      .listProdutos(busca)
      .then((lista) => {
        if (valeu) setProdutos(lista.filter((p) => p.ativo));
      })
      .catch(() => undefined);
    return () => {
      valeu = false;
    };
  }, [aberto, busca]);

  const produto = produtos.find((p) => p.id === produtoId);

  /* A unidade acompanha o produto escolhido: o caso comum é consumir na unidade base, e
     obrigar a escolher de novo a cada produto seria atrito sem motivo. */
  useEffect(() => {
    if (produto) setUnidadeId(produto.unidade_id);
  }, [produto]);

  /* A estimativa aparece antes de enviar. Sem isso, produto sem preço de custo só revelaria
     o problema na recusa do servidor — e quem está lançando dez linhas descobre tarde. */
  const unidade = unidades.find((u) => u.id === unidadeId);
  const base = unidades.find((u) => u.id === produto?.unidade_id);
  let estimativa: string | null = null;
  if (produto && !valor.trim() && quantidade.trim()) {
    if (produto.preco_custo === null) {
      estimativa = "Este produto não tem preço de custo. Informe o valor.";
    } else if (unidade && base) {
      const naBase = Number(quantidade) * (Number(unidade.fator) / Number(base.fator));
      const conta = Number(produto.preco_custo) * naBase;
      if (Number.isFinite(conta)) {
        estimativa = `Estimado em ${brl(conta.toFixed(2))}, pelo preço de custo do produto.`;
      }
    }
  }

  return (
    <Modal
      open={aberto}
      title="Lançar consumo"
      description="O que saiu do estoque sem ser venda, e contra qual centro."
      onClose={onFechar}
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="ghost" inline onClick={onFechar}>
            Voltar
          </Button>
          <Button
            inline
            loading={busy}
            disabled={!produtoId || !quantidade.trim() || !centro || !unidadeId}
            onClick={() =>
              onLancar({
                produto_id: produtoId,
                centro_custo_id: centro,
                quantidade,
                unidade_id: unidadeId,
                valor: valor || null,
                observacao: observacao || null,
              })
            }
          >
            Lançar
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <TextField
          label="Buscar produto"
          value={busca}
          onChange={(evento) => setBusca(evento.target.value)}
          placeholder="Código, código de barras ou nome"
          hint="Sem busca, aparece o começo do catálogo."
        />
        <Select
          label="Produto"
          value={produtoId}
          onChange={setProdutoId}
          placeholder="Escolha um"
          options={produtos.map((p) => ({ value: p.id, label: `${p.codigo} · ${p.nome}` }))}
          empty="Nenhum produto encontrado."
        />
        <TextField
          label="Quantidade"
          inputMode="decimal"
          value={quantidade}
          onChange={(evento) => setQuantidade(evento.target.value)}
        />
        <Select
          label="Unidade"
          value={unidadeId}
          onChange={setUnidadeId}
          placeholder="Escolha uma"
          options={unidades.map((u) => ({ value: u.id, label: u.nome }))}
          empty="Nenhuma unidade cadastrada."
        />

        <div className="flex flex-col gap-2">
          <Select
            label="Centro de custo"
            value={centro}
            onChange={setCentro}
            placeholder="Escolha um"
            options={centros.map((c) => ({ value: c.id, label: c.nome }))}
            hint="Obrigatório: um consumo sem centro não responde nada."
            empty="Nenhum centro de custo ainda."
          />
          <div>
            <Button variant="ghost" inline onClick={onNovoCentro}>
              + Novo centro de custo
            </Button>
          </div>
        </div>

        <TextField
          label="Valor"
          leading="R$"
          inputMode="decimal"
          value={valor}
          onChange={(evento) => setValor(evento.target.value)}
          hint={estimativa ?? "Em branco, vale o preço de custo do produto."}
          invalid={estimativa?.startsWith("Este produto não tem") ?? false}
        />
        <TextField
          label="Observação"
          value={observacao}
          onChange={(evento) => setObservacao(evento.target.value)}
          hint="Opcional. Onde foi usado, por exemplo: talhão 7."
        />
      </div>
    </Modal>
  );
}

function ConsumosDoMes({
  aberto,
  consumos,
  onFechar,
}: {
  aberto: boolean;
  consumos: ConsumoRegistrado[];
  onFechar: () => void;
}) {
  return (
    <Modal
      open={aberto}
      largura="ampla"
      title="Consumos do mês"
      description="Cada saída de estoque que virou custo, com o que ela custou."
      onClose={onFechar}
    >
      {consumos.length === 0 ? (
        <p className="py-6 text-center text-base text-ink-muted">
          Nada consumido neste mês.
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {consumos.map((consumo) => (
            <li key={consumo.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="text-base text-ink">{consumo.produto_nome}</p>
                <p className="truncate text-sm text-ink-faint">
                  {[
                    /* `num` e não o texto cru: o servidor guarda a quantidade com seis
                       casas, e "25.000000" na tela é número de banco de dados, não de
                       quem lançou 25 sacos. */
                    `${num(consumo.quantidade, 3)} · ${consumo.centro_nome}`,
                    dateBr(consumo.ocorrido_em.slice(0, 10)),
                    consumo.observacao,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <span className="shrink-0 text-base font-medium text-ink">
                {brl(consumo.valor)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
