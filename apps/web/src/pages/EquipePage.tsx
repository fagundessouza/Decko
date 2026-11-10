import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { equipe } from "../lib/api";
import type { Membro, Papel } from "../lib/api";

interface Props {
  onBack: () => void;
  /** Quem está olhando. Ninguém mexe nos próprios papéis nem desliga o próprio acesso. */
  meuId: string;
}

function motivoDoErro(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* A equipe da loja.
 *
 * Até 10/11/2026 não havia como o dono criar o operador dele: as permissões existiam no
 * manifesto e nenhuma rota por trás, e só a linha de comando do servidor criava gente.
 *
 * Duas regras daqui não são detalhe de interface, e sim a `docs/adr/0020-operador-supervisor-e-papeis.md`:
 *
 * 1. **A senha inicial é do dono, e dura uma entrada.** Quem é criado aqui é obrigado a
 *    trocá-la — enquanto o dono souber a senha do operador, "quem fez" é contestável.
 * 2. **O papel é a fronteira.** O que o operador não pode nem chega no token dele, então a
 *    tela dele não tem o que esconder.
 *
 * Um papel por pessoa, nesta versão: é o que os papéis semeados preveem. Quem já tiver
 * mais de um aparece com todos, e trocar aqui substitui o conjunto.
 */
export function EquipePage({ onBack, meuId }: Props) {
  const [membros, setMembros] = useState<Membro[] | null>(null);
  const [papeis, setPapeis] = useState<Papel[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [convidando, setConvidando] = useState(false);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [papelEscolhido, setPapelEscolhido] = useState("");

  const [trocandoPapel, setTrocandoPapel] = useState<Membro | null>(null);
  const [novoPapel, setNovoPapel] = useState("");

  async function carregar() {
    setErro(null);
    try {
      const [lista, todos] = await Promise.all([equipe.listar(), equipe.papeis()]);
      setMembros(lista);
      setPapeis(todos);
      if (todos.length > 0) setPapelEscolhido((atual) => atual || todos[0].id);
    } catch (cause) {
      setErro(motivoDoErro(cause, "Não foi possível carregar a equipe."));
      setMembros([]);
    }
  }

  useEffect(() => {
    void carregar();
    // Uma vez, na abertura: recarregar a cada render faria a lista piscar a cada clique.
  }, []);

  async function operar(acao: () => Promise<unknown>, padrao: string) {
    setBusy(true);
    setErro(null);
    try {
      await acao();
      await carregar();
    } catch (cause) {
      setErro(motivoDoErro(cause, padrao));
    } finally {
      setBusy(false);
    }
  }

  async function convidar() {
    setConvidando(false);
    await operar(
      () =>
        equipe.criar({
          email: email.trim(),
          full_name: nome.trim(),
          senha_inicial: senha,
          papeis: papelEscolhido ? [papelEscolhido] : [],
        }),
      "Não foi possível criar a pessoa.",
    );
    setNome("");
    setEmail("");
    setSenha("");
  }

  async function aplicarPapel() {
    const alvo = trocandoPapel;
    setTrocandoPapel(null);
    if (!alvo) return;
    await operar(
      () => equipe.definirPapeis(alvo.id, novoPapel ? [novoPapel] : []),
      "Não foi possível trocar o papel.",
    );
  }

  const descricaoDoPapel = (id: string) => papeis.find((p) => p.id === id)?.description ?? "";

  return (
    <Page>
      <PageHeader
        title="Equipe"
        description="Quem trabalha na loja, e o que cada um alcança no sistema."
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <Card>
        <CardHeader
          title="Pessoas"
          description={
            membros === null
              ? undefined
              : `${membros.length} ${membros.length === 1 ? "pessoa" : "pessoas"} nesta empresa.`
          }
          action={
            <Button
              variant="secondary"
              inline
              disabled={busy || papeis.length === 0}
              onClick={() => setConvidando(true)}
            >
              Nova pessoa
            </Button>
          }
        />
        {membros === null ? (
          <CardBody>
            <p className="animate-fade text-base text-ink-muted">Carregando…</p>
          </CardBody>
        ) : (
          <ul className="mt-2">
            {membros.map((membro) => (
              <li
                key={membro.id}
                className="flex flex-col gap-3 border-b border-line-subtle px-5 py-4 last:border-0
                           sm:flex-row sm:items-center sm:justify-between sm:px-6"
              >
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-base font-medium text-ink">
                      {membro.full_name}
                    </span>
                    {!membro.is_active && <Badge tone="neutral">Desligado</Badge>}
                    {membro.must_change_password && (
                      <Badge tone="warn">Senha ainda é a inicial</Badge>
                    )}
                  </span>
                  <span className="block truncate text-sm text-ink-faint">{membro.email}</span>
                  <span className="block truncate text-sm text-ink-muted">
                    {membro.papeis.length === 0
                      ? "Sem papel: entra e não alcança nada."
                      : membro.papeis.map((p) => p.name).join(", ")}
                  </span>
                </span>

                {membro.id !== meuId && (
                  <span className="flex shrink-0 flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      inline
                      disabled={busy}
                      onClick={() => {
                        setTrocandoPapel(membro);
                        setNovoPapel(membro.papeis[0]?.id ?? "");
                      }}
                    >
                      Trocar papel
                    </Button>
                    <Button
                      variant="secondary"
                      inline
                      disabled={busy}
                      onClick={() =>
                        void operar(
                          () => equipe.definirSituacao(membro.id, !membro.is_active),
                          "Não foi possível mudar o acesso.",
                        )
                      }
                    >
                      {membro.is_active ? "Desligar acesso" : "Religar acesso"}
                    </Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {papeis.length > 0 && (
        <div className="mt-6">
          <Card>
            <CardHeader
              title="Papéis"
              description="O que cada papel concede. Escolher o papel é escolher o que a pessoa alcança."
            />
            <ul className="mt-2">
              {papeis.map((papel) => (
                <li
                  key={papel.id}
                  className="flex items-center justify-between gap-4 border-b border-line-subtle
                             px-5 py-3 last:border-0 sm:px-6"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-base text-ink">{papel.name}</span>
                    <span className="block truncate text-sm text-ink-faint">
                      {papel.description ?? "—"}
                    </span>
                  </span>
                  <span className="shrink-0 text-sm tabular-nums text-ink-muted">
                    {papel.permissoes.length}{" "}
                    {papel.permissoes.length === 1 ? "permissão" : "permissões"}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      <Modal
        open={convidando}
        title="Nova pessoa"
        description="Ela entra com a senha que você definir, e é obrigada a trocá-la."
        onClose={() => setConvidando(false)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setConvidando(false)}>
              Cancelar
            </Button>
            <Button
              inline
              disabled={nome.trim() === "" || email.trim() === "" || senha.length < 8}
              onClick={() => void convidar()}
            >
              Criar acesso
            </Button>
          </div>
        }
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void convidar();
          }}
        >
          <TextField
            label="Nome"
            value={nome}
            onChange={(event) => setNome(event.target.value)}
          />
          <TextField
            label="E-mail"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            hint="É com ele que a pessoa entra, junto do código desta empresa."
          />
          <TextField
            label="Senha inicial"
            type="password"
            revealable
            value={senha}
            onChange={(event) => setSenha(event.target.value)}
            hint="Ao menos 8 caracteres. Ela troca na primeira entrada, e aí você deixa de saber."
          />
          <Select
            label="Papel"
            value={papelEscolhido}
            onChange={setPapelEscolhido}
            options={papeis.map((p) => ({ value: p.id, label: p.name }))}
            hint={descricaoDoPapel(papelEscolhido)}
          />
        </form>
      </Modal>

      <Modal
        open={trocandoPapel !== null}
        title={`Papel de ${trocandoPapel?.full_name ?? ""}`}
        description="Muda o que a pessoa alcança a partir da próxima entrada dela."
        onClose={() => setTrocandoPapel(null)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setTrocandoPapel(null)}>
              Cancelar
            </Button>
            <Button inline onClick={() => void aplicarPapel()}>
              Salvar papel
            </Button>
          </div>
        }
      >
        <Select
          label="Papel"
          value={novoPapel}
          onChange={setNovoPapel}
          options={papeis.map((p) => ({ value: p.id, label: p.name }))}
          hint={descricaoDoPapel(novoPapel)}
        />
      </Modal>
    </Page>
  );
}
