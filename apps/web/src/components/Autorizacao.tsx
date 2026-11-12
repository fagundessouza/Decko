import { useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "../lib/api";
import { pdv } from "../lib/pdv";
import type { Autorizador, Credencial } from "../lib/pdv";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { Modal } from "./Modal";
import { Select } from "./Select";
import { TextField } from "./TextField";

type Acao = (credencial?: Credencial) => Promise<unknown>;

/* A liberação do supervisor, no balcão.
 *
 * O desenho inteiro está em `docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 4, e
 * duas coisas dele valem aqui:
 *
 * 1. **A tela não decide nada.** Ela tenta a ação; se o servidor responder 428, pede a
 *    credencial e **repete a ação** com ela. Nenhum botão é destravado, porque destravar
 *    botão é teatro — quem abre o inspetor passa por cima.
 * 2. **A senha não fica.** Ela é usada na requisição seguinte e o campo é limpo. Nada de
 *    guardar a liberação do supervisor "para as próximas", que é como uma trava vira
 *    hábito e o hábito vira buraco.
 */
export function useAutorizacao(opcoes: { nested?: boolean } = {}): {
  executar: (acao: Acao) => Promise<void>;
  dialogo: ReactNode;
} {
  const [pendente, setPendente] = useState<{ acao: Acao } | null>(null);
  const [quem, setQuem] = useState<Autorizador[]>([]);
  const [escolhido, setEscolhido] = useState("");
  const [senha, setSenha] = useState("");
  /* PIN é o padrão porque isto acontece no balcão, com fila esperando: o supervisor
   * chamado para liberar um cancelamento digita quatro dígitos, não uma senha longa.
   * A senha continua à mão para quem ainda não definiu PIN, ou está bloqueado. */
  const [comSenha, setComSenha] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function fechar() {
    setPendente(null);
    setSenha("");
    setErro(null);
  }

  async function executar(acao: Acao) {
    try {
      await acao();
    } catch (cause) {
      // 428 é o servidor dizendo "pode, com a liberação de alguém". Qualquer outro erro
      // é da ação e sobe para quem chamou tratar.
      if (!(cause instanceof ApiError) || cause.status !== 428) throw cause;

      const lista = await pdv.autorizadores().catch(() => []);
      setQuem(lista);
      setEscolhido((atual) => atual || lista[0]?.id || "");
      setSenha("");
      setErro(null);
      setPendente({ acao });
    }
  }

  async function liberar() {
    if (!pendente || !escolhido) return;
    setBusy(true);
    setErro(null);
    try {
      await pendente.acao(
        comSenha
          ? { autorizador_id: escolhido, senha }
          : { autorizador_id: escolhido, pin: senha },
      );
      fechar();
    } catch (cause) {
      // O erro fica **dentro** do diálogo e ele continua aberto: senha errada no balcão
      // é para digitar de novo, não para recomeçar a operação.
      setErro(cause instanceof Error && cause.message ? cause.message : "Não foi liberado.");
      setSenha("");
    } finally {
      setBusy(false);
    }
  }

  const dialogo = (
    <Modal
      open={pendente !== null}
      nested={opcoes.nested ?? false}
      title="Liberação do supervisor"
      description="Esta ação precisa de alguém que possa liberá-la. Chame a pessoa e peça a senha dela."
      onClose={fechar}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" inline onClick={fechar}>
            Cancelar
          </Button>
          <Button inline loading={busy} disabled={!escolhido || senha === ""} onClick={() => void liberar()}>
            Liberar
          </Button>
        </div>
      }
    >
      {erro && (
        <div className="mb-4">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void liberar();
        }}
      >
        <Select
          label="Quem está liberando"
          value={escolhido}
          onChange={setEscolhido}
          options={quem.map((pessoa) => ({ value: pessoa.id, label: pessoa.nome }))}
          empty="Ninguém nesta empresa pode liberar. Fale com o dono."
        />
        <TextField
          label={comSenha ? "Senha de quem libera" : "PIN de quem libera"}
          type="password"
          revealable={comSenha}
          inputMode={comSenha ? undefined : "numeric"}
          value={senha}
          onChange={(event) => setSenha(event.target.value)}
          hint="Fica nesta requisição e não é guardada."
        />
        <button
          type="button"
          onClick={() => {
            setComSenha((atual) => !atual);
            setSenha("");
            setErro(null);
          }}
          className="self-start text-sm font-medium text-brand-link hover:underline"
        >
          {comSenha ? "Usar o PIN" : "Usar a senha"}
        </button>
      </form>
    </Modal>
  );

  return { executar, dialogo };
}
