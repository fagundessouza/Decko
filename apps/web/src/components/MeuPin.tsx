import { useEffect, useState } from "react";

import { equipe } from "../lib/api";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { Modal } from "./Modal";
import { TextField } from "./TextField";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Já tem PIN: a tela diz que vai substituir, em vez de deixar a pessoa na dúvida. */
  jaTem?: boolean;
}

/* O PIN de entrada rápida, definido pela própria pessoa.
 *
 * Confirmar com a senha é o que mantém o PIN **dela**: sem isso, um terminal deixado
 * aberto no balcão permitiria a qualquer um gravar um PIN próprio na conta alheia e
 * voltar nela quando quisesse. O dono consegue **apagar** um PIN esquecido, nunca
 * escolher um — ver `docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 1.
 */
export function MeuPin({ open, onClose, jaTem = false }: Props) {
  const [senha, setSenha] = useState("");
  const [pin, setPin] = useState("");
  const [repetido, setRepetido] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [pronto, setPronto] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSenha("");
    setPin("");
    setRepetido("");
    setErro(null);
    setPronto(false);
  }, [open]);

  const curto = pin !== "" && (pin.length < 4 || !/^\d+$/.test(pin));
  const diferentes = repetido !== "" && pin !== repetido;
  const podeSalvar = senha !== "" && pin.length >= 4 && /^\d+$/.test(pin) && pin === repetido;

  async function salvar() {
    setBusy(true);
    setErro(null);
    try {
      await equipe.definirPin(senha, pin);
      setPronto(true);
    } catch (cause) {
      setErro(
        cause instanceof Error && cause.message ? cause.message : "Não foi possível salvar o PIN.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Meu PIN"
      description={
        jaTem
          ? "Define um PIN novo no lugar do atual, para assumir a estação sem digitar a senha."
          : "Um atalho para assumir a estação sem digitar empresa, e-mail e senha."
      }
      onClose={onClose}
      footer={
        pronto ? (
          <div className="flex justify-end">
            <Button inline onClick={onClose}>
              Fechar
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={onClose}>
              Cancelar
            </Button>
            <Button inline loading={busy} disabled={!podeSalvar} onClick={() => void salvar()}>
              Salvar PIN
            </Button>
          </div>
        )
      }
    >
      {pronto ? (
        <p className="text-base text-ink">
          PIN guardado. Agora você assume a estação escolhendo o seu nome, ou passando o
          crachá, e digitando esses números.
        </p>
      ) : (
        <>
          {erro && (
            <div className="mb-4">
              <Alert tone="danger">{erro}</Alert>
            </div>
          )}
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (podeSalvar) void salvar();
            }}
          >
            <TextField
              label="Sua senha"
              type="password"
              revealable
              autoFocus
              value={senha}
              onChange={(event) => setSenha(event.target.value)}
              hint="Confirma que é você. Sem isso, qualquer um gravaria um PIN na sua conta."
            />
            <TextField
              label="PIN novo"
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              invalid={curto}
              hint="Só números, de 4 a 8 dígitos."
            />
            <TextField
              label="Repita o PIN"
              type="password"
              inputMode="numeric"
              value={repetido}
              onChange={(event) => setRepetido(event.target.value)}
              invalid={diferentes}
              hint={diferentes ? "Os dois não estão iguais." : undefined}
            />
          </form>
        </>
      )}
    </Modal>
  );
}
