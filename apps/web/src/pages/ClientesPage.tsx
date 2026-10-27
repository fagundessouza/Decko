import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, Row } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { clientes } from "../lib/clientes";
import type { Cliente, ClienteIn, TipoPessoa } from "../lib/clientes";
import { formatCpfCnpj } from "../lib/documents";

interface Props {
  onBack: () => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/** Campo em branco é ausência, não string vazia: o servidor guarda nulo. */
function ouNulo(valor: string): string | null {
  return valor.trim() === "" ? null : valor.trim();
}

const VAZIO = {
  tipo: "fisica" as TipoPessoa,
  nome: "",
  apelido: "",
  cpf_cnpj: "",
  inscricao_estadual: "",
  email: "",
  telefone: "",
  cep: "",
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "",
  uf: "",
  observacao: "",
};

type Formulario = typeof VAZIO;

function doCliente(cliente: Cliente): Formulario {
  return {
    tipo: cliente.tipo,
    nome: cliente.nome,
    apelido: cliente.apelido ?? "",
    cpf_cnpj: cliente.cpf_cnpj ? formatCpfCnpj(cliente.cpf_cnpj) : "",
    inscricao_estadual: cliente.inscricao_estadual ?? "",
    email: cliente.email ?? "",
    telefone: cliente.telefone ?? "",
    cep: cliente.cep ?? "",
    logradouro: cliente.logradouro ?? "",
    numero: cliente.numero ?? "",
    complemento: cliente.complemento ?? "",
    bairro: cliente.bairro ?? "",
    cidade: cliente.cidade ?? "",
    uf: cliente.uf ?? "",
    observacao: cliente.observacao ?? "",
  };
}

/* O cadastro de clientes.
 *
 * Dado pessoal: toda alteração vira linha na trilha de auditoria, e o cadastro não é
 * apagado — desativar tira das telas de lançamento sem deixar venda e nota apontando
 * para o vazio. */
export function ClientesPage({ onBack }: Props) {
  const [lista, setLista] = useState<Cliente[] | null>(null);
  const [busca, setBusca] = useState("");
  const [incluirInativos, setIncluirInativos] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [editando, setEditando] = useState<Cliente | null>(null);
  const [form, setForm] = useState<Formulario>(VAZIO);
  const [aberto, setAberto] = useState(false);

  function recarregar(termo = busca, inativos = incluirInativos) {
    return clientes
      .listar(termo, inativos)
      .then(setLista)
      .catch((cause) => {
        setLista([]);
        setErro(motivo(cause, "Não foi possível carregar os clientes."));
      });
  }

  useEffect(() => {
    void recarregar("", false);
  }, []);

  // Busca no servidor, com uma pausa para não disparar a cada tecla.
  useEffect(() => {
    const id = setTimeout(() => void recarregar(busca, incluirInativos), 250);
    return () => clearTimeout(id);
  }, [busca, incluirInativos]);

  function abrirNovo() {
    setEditando(null);
    setForm(VAZIO);
    setErro(null);
    setAberto(true);
  }

  function abrirEdicao(cliente: Cliente) {
    setEditando(cliente);
    setForm(doCliente(cliente));
    setErro(null);
    setAberto(true);
  }

  async function salvar() {
    setBusy(true);
    setErro(null);
    const corpo: ClienteIn = {
      tipo: form.tipo,
      nome: form.nome.trim(),
      apelido: ouNulo(form.apelido),
      cpf_cnpj: ouNulo(form.cpf_cnpj),
      inscricao_estadual: ouNulo(form.inscricao_estadual),
      email: ouNulo(form.email),
      telefone: ouNulo(form.telefone),
      cep: ouNulo(form.cep),
      logradouro: ouNulo(form.logradouro),
      numero: ouNulo(form.numero),
      complemento: ouNulo(form.complemento),
      bairro: ouNulo(form.bairro),
      cidade: ouNulo(form.cidade),
      uf: ouNulo(form.uf),
      observacao: ouNulo(form.observacao),
    };

    try {
      if (editando) await clientes.atualizar(editando.id, corpo);
      else await clientes.criar(corpo);
      setAberto(false);
      await recarregar();
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível salvar o cliente."));
    } finally {
      setBusy(false);
    }
  }

  async function alternarAtivo(cliente: Cliente) {
    setBusy(true);
    setErro(null);
    try {
      if (cliente.ativo) await clientes.desativar(cliente.id);
      else await clientes.reativar(cliente.id);
      await recarregar();
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível mudar a situação do cliente."));
    } finally {
      setBusy(false);
    }
  }

  const campo = (chave: keyof Formulario) => ({
    value: form[chave],
    onChange: (event: { target: { value: string } }) =>
      setForm((atual) => ({ ...atual, [chave]: event.target.value })),
  });

  return (
    <Page wide>
      <PageHeader
        title="Clientes"
        description="Quem compra de você."
        onBack={onBack}
        action={
          <Button inline onClick={abrirNovo}>
            Novo cliente
          </Button>
        }
      />

      {erro && !aberto && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <TextField
            label="Procurar"
            leading="⌕"
            placeholder="Nome, apelido ou CPF/CNPJ"
            value={busca}
            onChange={(event) => setBusca(event.target.value)}
          />
        </div>
        <Button
          variant={incluirInativos ? "secondary" : "ghost"}
          inline
          onClick={() => setIncluirInativos((valor) => !valor)}
        >
          {incluirInativos ? "Ocultar inativos" : "Mostrar inativos"}
        </Button>
      </div>

      {lista === null && <p className="animate-fade text-base text-ink-muted">Carregando…</p>}

      {lista !== null && lista.length === 0 && (
        <Card muted>
          <CardBody className="text-center">
            <p className="text-base text-ink-muted">
              {busca.trim()
                ? "Nenhum cliente com esse nome ou documento."
                : "Nenhum cliente cadastrado ainda."}
            </p>
          </CardBody>
        </Card>
      )}

      {lista !== null && lista.length > 0 && (
        <Card>
          <ul>
            {lista.map((cliente) => (
              <Row key={cliente.id}>
                <button
                  type="button"
                  onClick={() => abrirEdicao(cliente)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate font-medium text-ink">
                    {cliente.nome}
                    {cliente.apelido ? ` · ${cliente.apelido}` : ""}
                  </span>
                  <span className="block truncate text-sm tabular-nums text-ink-muted">
                    {cliente.cpf_cnpj ? formatCpfCnpj(cliente.cpf_cnpj) : "Sem documento"}
                    {cliente.cidade ? ` · ${cliente.cidade}` : ""}
                    {cliente.uf ? `/${cliente.uf}` : ""}
                  </span>
                </button>

                <div className="flex shrink-0 items-center gap-3">
                  {!cliente.ativo && <Badge tone="neutral">Inativo</Badge>}
                  <Button
                    variant="ghost"
                    inline
                    disabled={busy}
                    onClick={() => void alternarAtivo(cliente)}
                  >
                    {cliente.ativo ? "Desativar" : "Reativar"}
                  </Button>
                </div>
              </Row>
            ))}
          </ul>
        </Card>
      )}

      <Modal
        open={aberto}
        title={editando ? "Editar cliente" : "Novo cliente"}
        description="O documento é conferido pelo dígito. Cliente de balcão pode ficar sem."
        onClose={() => setAberto(false)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setAberto(false)}>
              Cancelar
            </Button>
            <Button inline loading={busy} disabled={!form.nome.trim()} onClick={() => void salvar()}>
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

          <Select
            label="Tipo"
            value={form.tipo}
            onChange={(valor) => setForm((atual) => ({ ...atual, tipo: valor as TipoPessoa }))}
            options={[
              { value: "fisica", label: "Pessoa física" },
              { value: "juridica", label: "Empresa" },
            ]}
          />

          <TextField
            label={form.tipo === "juridica" ? "Razão social" : "Nome"}
            required
            {...campo("nome")}
          />
          {form.tipo === "juridica" && (
            <TextField
              label="Nome de fantasia"
              hint="Como a loja é conhecida. A nota sai com a razão social."
              {...campo("apelido")}
            />
          )}

          <TextField
            label={form.tipo === "juridica" ? "CNPJ" : "CPF"}
            hint="Opcional."
            inputMode="numeric"
            {...campo("cpf_cnpj")}
          />
          {form.tipo === "juridica" && (
            <TextField
              label="Inscrição estadual"
              hint='Opcional. "Isento" também vale.'
              {...campo("inscricao_estadual")}
            />
          )}

          <TextField label="E-mail" type="email" {...campo("email")} />
          <TextField label="Telefone" inputMode="tel" {...campo("telefone")} />

          <div className="grid gap-4 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <TextField label="CEP" inputMode="numeric" {...campo("cep")} />
            <TextField label="Logradouro" {...campo("logradouro")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <TextField label="Número" {...campo("numero")} />
            <TextField label="Complemento" {...campo("complemento")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_5rem]">
            <TextField label="Bairro" {...campo("bairro")} />
            <TextField label="Cidade" {...campo("cidade")} />
            <TextField label="UF" maxLength={2} {...campo("uf")} />
          </div>

          <TextField label="Observação" {...campo("observacao")} />
        </form>
      </Modal>
    </Page>
  );
}
